"""PocketCam Bridge: use an ARKit iPhone as a Blender virtual camera."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Matrix, Quaternion, Vector

from .server import PROTOCOL_VERSION, PoseServer, discover_local_ip


bl_info = {
    "name": "PocketCam Bridge",
    "author": "Open-source prototype created with Codex",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > PocketCam",
    "description": "Drive and record a Blender camera from an ARKit iPhone",
    "category": "Animation",
}


_server: PoseServer | None = None
_state: dict[str, Any] = {
    "reference_pose": None,
    "camera_start": None,
    "latest_pose": None,
    "pending_recenter": True,
    "smoothed_location": None,
    "smoothed_rotation": None,
    "recording": False,
    "record_start_clock": 0.0,
    "record_start_frame": 1,
    "last_record_frame": None,
    "take_name": "",
    "last_status_signature": None,
}


def _camera_poll(_self: Any, obj: bpy.types.Object) -> bool:
    return obj is not None and obj.type == "CAMERA"


class PocketCamSettings(PropertyGroup):
    port: IntProperty(name="Port", default=8766, min=1024, max=65535)
    camera: PointerProperty(name="Camera", type=bpy.types.Object, poll=_camera_poll)
    movement_scale: FloatProperty(
        name="Movement Scale",
        description="Virtual meters travelled for each physical meter",
        default=1.0,
        min=0.01,
        max=100.0,
        soft_max=20.0,
    )
    smoothing: FloatProperty(
        name="Smoothing",
        description="Higher values remove more hand jitter but add latency",
        default=0.18,
        min=0.0,
        max=0.95,
    )
    lens_mm: FloatProperty(name="Lens", default=18.0, min=1.0, max=300.0, subtype="DISTANCE")
    use_phone_lens: BoolProperty(name="Use Phone Lens Control", default=True)
    status: StringProperty(name="Status", default="Stopped")
    address: StringProperty(name="Address", default="")


def _settings(scene: bpy.types.Scene | None = None) -> PocketCamSettings | None:
    scene = scene or getattr(bpy.context, "scene", None)
    return getattr(scene, "pocketcam_settings", None) if scene else None


def _selected_camera(scene: bpy.types.Scene, settings: PocketCamSettings) -> bpy.types.Object | None:
    camera = settings.camera
    if camera is None and scene.camera is not None and scene.camera.type == "CAMERA":
        camera = scene.camera
        settings.camera = camera
    if camera is None:
        camera_data = bpy.data.cameras.new("PocketCam Camera")
        camera = bpy.data.objects.new("PocketCam Camera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        settings.camera = camera
    return camera


def _pose_matrix(payload: dict[str, Any]) -> Matrix | None:
    position = payload.get("position")
    rotation = payload.get("rotation")
    if not (
        isinstance(position, list)
        and len(position) == 3
        and isinstance(rotation, list)
        and len(rotation) == 4
    ):
        return None
    try:
        location = Vector(tuple(float(value) for value in position))
        # Wire order is x, y, z, w; mathutils expects w, x, y, z.
        quaternion = Quaternion(
            (
                float(rotation[3]),
                float(rotation[0]),
                float(rotation[1]),
                float(rotation[2]),
            )
        ).normalized()
    except (TypeError, ValueError, OverflowError):
        return None
    matrix = quaternion.to_matrix().to_4x4()
    matrix.translation = location
    return matrix


def _reset_tracking_reference(camera: bpy.types.Object, pose: Matrix) -> None:
    _state["reference_pose"] = pose.copy()
    _state["camera_start"] = camera.matrix_world.copy()
    _state["pending_recenter"] = False
    _state["smoothed_location"] = camera.matrix_world.translation.copy()
    _state["smoothed_rotation"] = camera.matrix_world.to_quaternion().copy()


def _apply_pose(scene: bpy.types.Scene, settings: PocketCamSettings, payload: dict[str, Any]) -> None:
    camera = _selected_camera(scene, settings)
    if camera is None:
        return
    pose = _pose_matrix(payload)
    if pose is None:
        settings.status = "Invalid pose packet"
        return
    _state["latest_pose"] = pose.copy()

    if _state["pending_recenter"] or _state["reference_pose"] is None:
        _reset_tracking_reference(camera, pose)

    reference: Matrix = _state["reference_pose"]
    camera_start: Matrix = _state["camera_start"]
    delta = reference.inverted_safe() @ pose
    delta.translation = delta.translation * float(settings.movement_scale)
    target = camera_start @ delta
    target_location, target_rotation, _target_scale = target.decompose()

    alpha = max(0.01, min(1.0, 1.0 - float(settings.smoothing)))
    current_location: Vector | None = _state["smoothed_location"]
    current_rotation: Quaternion | None = _state["smoothed_rotation"]
    if current_location is None or current_rotation is None:
        current_location = target_location.copy()
        current_rotation = target_rotation.copy()
    else:
        current_location = current_location.lerp(target_location, alpha)
        current_rotation = current_rotation.slerp(target_rotation, alpha)

    _state["smoothed_location"] = current_location.copy()
    _state["smoothed_rotation"] = current_rotation.copy()
    camera.rotation_mode = "QUATERNION"
    # Apply in world space so parented cameras behave exactly like unparented ones.
    # Assigning location/rotation directly would treat these values as parent-local.
    camera.matrix_world = Matrix.LocRotScale(
        current_location,
        current_rotation,
        Vector((1.0, 1.0, 1.0)),
    )
    if settings.use_phone_lens:
        camera.data.lens = float(settings.lens_mm)

    if _state["recording"]:
        _record_keyframe(scene, camera)


def _start_recording(scene: bpy.types.Scene, settings: PocketCamSettings) -> None:
    camera = _selected_camera(scene, settings)
    if camera is None or _state["recording"]:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    take_name = f"PocketCam_Take_{stamp}"
    if camera.animation_data is None:
        camera.animation_data_create()
    if camera.animation_data.action is not None:
        camera.animation_data.action.use_fake_user = True
    camera.animation_data.action = bpy.data.actions.new(take_name)
    if camera.data.animation_data is None:
        camera.data.animation_data_create()
    if camera.data.animation_data.action is not None:
        camera.data.animation_data.action.use_fake_user = True
    camera.data.animation_data.action = bpy.data.actions.new(f"{take_name}_Lens")
    camera.rotation_mode = "QUATERNION"

    _state["recording"] = True
    _state["record_start_clock"] = time.perf_counter()
    _state["record_start_frame"] = int(scene.frame_current)
    _state["last_record_frame"] = None
    _state["take_name"] = take_name
    settings.status = f"Recording {take_name}"
    _send_status(scene, force=True)


def _stop_recording(scene: bpy.types.Scene, settings: PocketCamSettings) -> None:
    if not _state["recording"]:
        return
    _state["recording"] = False
    settings.status = f"Recorded {_state['take_name']}"
    _send_status(scene, force=True)


def _record_keyframe(scene: bpy.types.Scene, camera: bpy.types.Object) -> None:
    fps = float(scene.render.fps) / max(0.001, float(scene.render.fps_base))
    elapsed = max(0.0, time.perf_counter() - float(_state["record_start_clock"]))
    frame = int(_state["record_start_frame"] + round(elapsed * fps))
    if frame == _state["last_record_frame"]:
        return
    _state["last_record_frame"] = frame
    camera.keyframe_insert(data_path="location", frame=frame, group="PocketCam Transform")
    camera.keyframe_insert(
        data_path="rotation_quaternion",
        frame=frame,
        group="PocketCam Transform",
    )
    camera.data.keyframe_insert(data_path="lens", frame=frame, group="PocketCam Lens")
    if frame > scene.frame_end:
        scene.frame_end = frame


def _camera_names() -> list[str]:
    return sorted(obj.name for obj in bpy.data.objects if obj.type == "CAMERA" and not obj.hide_get())


def _send_status(scene: bpy.types.Scene, force: bool = False, message: str = "") -> None:
    if _server is None or not _server.client_connected:
        return
    settings = _settings(scene)
    if settings is None:
        return
    camera = _selected_camera(scene, settings)
    payload = {
        "type": "status",
        "protocol": PROTOCOL_VERSION,
        "connected": True,
        "recording": bool(_state["recording"]),
        "tracking": settings.status,
        "available_cameras": _camera_names(),
        "selected_camera": camera.name if camera else None,
        "movement_scale": float(settings.movement_scale),
        "smoothing": float(settings.smoothing),
        "lens_mm": float(settings.lens_mm),
        "message": message,
    }
    signature = repr(payload)
    if force or signature != _state["last_status_signature"]:
        _server.send_json(payload)
        _state["last_status_signature"] = signature


def _handle_event(scene: bpy.types.Scene, settings: PocketCamSettings, kind: str, payload: dict[str, Any]) -> None:
    if kind == "server_started":
        settings.status = f"Listening on port {payload.get('port', settings.port)}"
    elif kind == "server_error":
        settings.status = f"Server error: {payload.get('message', 'unknown')}"
    elif kind == "client_connected":
        settings.status = f"Connected: {payload.get('host', 'iPhone')}"
        _state["pending_recenter"] = True
        _state["last_status_signature"] = None
        _send_status(scene, force=True, message="Connected to Blender")
    elif kind == "client_disconnected":
        if _state["recording"]:
            _stop_recording(scene, settings)
        settings.status = "Listening - iPhone disconnected"
    elif kind == "hello":
        _send_status(scene, force=True, message="Handshake accepted")
    elif kind == "ping":
        if _server:
            _server.send_json({"type": "pong", "timestamp": payload.get("timestamp")})
    elif kind == "protocol_error":
        settings.status = f"Protocol error: {payload.get('message', 'unknown')}"
    elif kind == "settings":
        try:
            if "movement_scale" in payload:
                settings.movement_scale = max(0.01, min(100.0, float(payload["movement_scale"])))
            if "smoothing" in payload:
                settings.smoothing = max(0.0, min(0.95, float(payload["smoothing"])))
            if "lens_mm" in payload:
                settings.lens_mm = max(1.0, min(300.0, float(payload["lens_mm"])))
        except (TypeError, ValueError):
            settings.status = "Ignored invalid phone settings"
        _send_status(scene, force=True)
    elif kind == "select_camera":
        name = str(payload.get("name", ""))
        camera = bpy.data.objects.get(name)
        if camera is not None and camera.type == "CAMERA":
            settings.camera = camera
            scene.camera = camera
            _state["pending_recenter"] = True
            _send_status(scene, force=True, message=f"Selected {name}")
    elif kind == "command":
        command = payload.get("command")
        if command == "recenter":
            _state["pending_recenter"] = True
            settings.status = "Recenter on next pose"
        elif command == "record_start":
            _start_recording(scene, settings)
        elif command == "record_stop":
            _stop_recording(scene, settings)
        _send_status(scene, force=True)


def _timer_tick() -> float:
    try:
        scene = getattr(bpy.context, "scene", None)
        settings = _settings(scene)
        if scene is None or settings is None or _server is None:
            return 0.05
        for event in _server.drain_events():
            _handle_event(scene, settings, event.kind, event.payload)
        pose = _server.pop_latest_pose()
        if pose is not None:
            _apply_pose(scene, settings, pose)
        if _server.client_connected and not _state["recording"] and settings.status.startswith("Listening"):
            settings.status = "Connected"
        return 0.01
    except Exception as exc:  # Keep Blender's timer alive and surface the problem.
        settings = _settings()
        if settings is not None:
            settings.status = f"PocketCam error: {exc}"
        return 0.1


class POCKETCAM_OT_start_server(Operator):
    bl_idname = "pocketcam.start_server"
    bl_label = "Start Server"
    bl_description = "Listen for the PocketCam iPhone app on the local network"

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _server
        settings = _settings(context.scene)
        if settings is None:
            return {"CANCELLED"}
        if _server is not None:
            _server.stop()
        _server = PoseServer(port=settings.port)
        _server.start()
        address = discover_local_ip()
        settings.address = address
        settings.status = f"Starting {address}:{settings.port}"
        _state["pending_recenter"] = True
        _state["last_status_signature"] = None
        return {"FINISHED"}


class POCKETCAM_OT_stop_server(Operator):
    bl_idname = "pocketcam.stop_server"
    bl_label = "Stop Server"

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _server
        settings = _settings(context.scene)
        if settings is not None and _state["recording"]:
            _stop_recording(context.scene, settings)
        if _server is not None:
            _server.stop()
            _server = None
        if settings is not None:
            settings.status = "Stopped"
        return {"FINISHED"}


class POCKETCAM_OT_recenter(Operator):
    bl_idname = "pocketcam.recenter"
    bl_label = "Recenter"
    bl_description = "Use the next phone pose as the new camera origin"

    def execute(self, context: bpy.types.Context) -> set[str]:
        _state["pending_recenter"] = True
        settings = _settings(context.scene)
        if settings is not None:
            settings.status = "Recenter on next pose"
        return {"FINISHED"}


class POCKETCAM_OT_record(Operator):
    bl_idname = "pocketcam.record"
    bl_label = "Record"

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = _settings(context.scene)
        if settings is None:
            return {"CANCELLED"}
        _start_recording(context.scene, settings)
        return {"FINISHED"}


class POCKETCAM_OT_stop_recording(Operator):
    bl_idname = "pocketcam.stop_recording"
    bl_label = "Stop Recording"

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = _settings(context.scene)
        if settings is None:
            return {"CANCELLED"}
        _stop_recording(context.scene, settings)
        return {"FINISHED"}


class POCKETCAM_OT_copy_address(Operator):
    bl_idname = "pocketcam.copy_address"
    bl_label = "Copy Address"

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = _settings(context.scene)
        if settings is None:
            return {"CANCELLED"}
        context.window_manager.clipboard = f"{settings.address}:{settings.port}"
        self.report({"INFO"}, "PocketCam address copied")
        return {"FINISHED"}


class POCKETCAM_PT_panel(Panel):
    bl_label = "PocketCam Bridge"
    bl_idname = "POCKETCAM_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PocketCam"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = _settings(context.scene)
        if settings is None:
            return
        box = layout.box()
        box.label(text=settings.status, icon="INFO")
        row = box.row(align=True)
        if _server is None or not _server.running:
            row.operator("pocketcam.start_server", icon="PLAY")
        else:
            row.operator("pocketcam.stop_server", icon="PAUSE")
        row.prop(settings, "port", text="")
        if settings.address:
            row = box.row(align=True)
            row.label(text=f"{settings.address}:{settings.port}", icon="URL")
            row.operator("pocketcam.copy_address", text="", icon="COPYDOWN")

        layout.prop(settings, "camera")
        layout.prop(settings, "movement_scale")
        layout.prop(settings, "smoothing")
        layout.prop(settings, "use_phone_lens")
        if settings.use_phone_lens:
            layout.prop(settings, "lens_mm")

        controls = layout.row(align=True)
        controls.operator("pocketcam.recenter", icon="ORIENTATION_GIMBAL")
        if _state["recording"]:
            controls.operator("pocketcam.stop_recording", icon="SNAP_FACE")
        else:
            controls.operator("pocketcam.record", icon="REC")


_classes = (
    PocketCamSettings,
    POCKETCAM_OT_start_server,
    POCKETCAM_OT_stop_server,
    POCKETCAM_OT_recenter,
    POCKETCAM_OT_record,
    POCKETCAM_OT_stop_recording,
    POCKETCAM_OT_copy_address,
    POCKETCAM_PT_panel,
)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pocketcam_settings = PointerProperty(type=PocketCamSettings)
    if not bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.register(_timer_tick, first_interval=0.05, persistent=True)


def unregister() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None
    if bpy.app.timers.is_registered(_timer_tick):
        bpy.app.timers.unregister(_timer_tick)
    if hasattr(bpy.types.Scene, "pocketcam_settings"):
        del bpy.types.Scene.pocketcam_settings
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
