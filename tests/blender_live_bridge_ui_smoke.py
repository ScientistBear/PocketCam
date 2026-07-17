"""End-to-end live bridge test for normal Blender with a GPU context."""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "blender_addon"))

import pocketcam_bridge as addon  # noqa: E402
from pocketcam_bridge.server import PoseServer  # noqa: E402


result_path = Path(os.environ["POCKETCAM_LIVE_SMOKE_RESULT"])
client_result: dict[str, object] = {}
deadline = time.time() + 10.0

addon.register()
scene = bpy.context.scene
settings = scene.pocketcam_settings
settings.smoothing = 0.0
settings.movement_scale = 1.0
settings.preview_enabled = True
settings.preview_fps = 8.0
settings.preview_width = 320

camera_data = bpy.data.cameras.new("PocketCam Live Test Camera")
camera = bpy.data.objects.new("PocketCam Live Test Camera", camera_data)
scene.collection.objects.link(camera)
camera.matrix_world = Matrix.Identity(4)
settings.camera = camera
scene.camera = camera
bpy.context.view_layer.update()

server = PoseServer(host="127.0.0.1", port=0)
addon._server = server
server.start()


def send(client: socket.socket, payload: dict) -> None:
    client.sendall(json.dumps(payload).encode("utf-8") + b"\n")


def phone_worker() -> None:
    try:
        bind_deadline = time.time() + 3.0
        while server.bound_port == 0 and time.time() < bind_deadline:
            time.sleep(0.01)
        with socket.create_connection(("127.0.0.1", server.bound_port), timeout=3.0) as client:
            client.settimeout(5.0)
            identity = {
                "type": "pose",
                "seq": 1,
                "timestamp": 1.0,
                "position": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "tracking": "Tracking",
            }
            send(client, {"type": "hello", "protocol": 1, "client": "live-smoke"})
            send(client, identity)
            time.sleep(0.2)
            send(client, dict(identity, seq=2, timestamp=2.0, position=[1.0, 2.0, 3.0]))

            buffer = bytearray()
            while time.time() < deadline:
                chunk = client.recv(64 * 1024)
                if not chunk:
                    break
                buffer.extend(chunk)
                while b"\n" in buffer:
                    raw, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    packet = json.loads(raw.decode("utf-8"))
                    if packet.get("type") == "preview":
                        jpeg = base64.b64decode(packet["data"])
                        if not jpeg.startswith(b"\xff\xd8"):
                            raise AssertionError("Phone received an invalid JPEG")
                        client_result["preview_bytes"] = len(jpeg)
                        return
            raise AssertionError("Phone did not receive a preview frame")
    except Exception:
        client_result["error"] = traceback.format_exc()


threading.Thread(target=phone_worker, name="PocketCamLiveSmokePhone", daemon=True).start()


def pump_bridge() -> float | None:
    try:
        addon._timer_tick()
        if "error" in client_result:
            raise AssertionError(str(client_result["error"]))
        pose_ready = addon._state["last_pose_sequence"] == 2
        preview_ready = "preview_bytes" in client_result
        if pose_ready and preview_ready:
            location = camera.matrix_world.translation
            expected = (1.0, 2.0, 3.0)
            if any(abs(actual - wanted) > 0.001 for actual, wanted in zip(location, expected)):
                raise AssertionError(f"Live camera pose mismatch: {tuple(location)}")
            if scene.camera is not camera:
                raise AssertionError("Live camera was not activated in the scene")
            result_path.write_text(
                f"POCKETCAM_LIVE_BRIDGE_UI_SMOKE_OK poses={addon._state['pose_packets']} "
                f"jpeg={client_result['preview_bytes']} bytes",
                encoding="utf-8",
            )
            return finish()
        if time.time() >= deadline:
            raise AssertionError("Timed out waiting for live pose and preview")
        return 0.01
    except Exception:
        result_path.write_text(traceback.format_exc(), encoding="utf-8")
        return finish()


def finish() -> None:
    server.stop()
    addon._server = None
    addon.unregister()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(pump_bridge, first_interval=0.25)
