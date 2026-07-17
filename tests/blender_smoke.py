"""Run with Blender's Python to exercise add-on registration and camera motion."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = Path(os.environ.get("POCKETCAM_ADDON_ROOT", PROJECT_ROOT / "blender_addon"))
sys.path.insert(0, str(ADDON_ROOT))

import pocketcam_bridge as addon  # noqa: E402


def close(actual: float, expected: float, tolerance: float = 0.001) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"Expected {expected}, got {actual}")


addon.register()
try:
    scene = bpy.context.scene
    settings = scene.pocketcam_settings
    settings.smoothing = 0.0
    settings.movement_scale = 1.0
    settings.lens_mm = 24.0

    camera_data = bpy.data.cameras.new("PocketCam Smoke Camera")
    camera = bpy.data.objects.new("PocketCam Smoke Camera", camera_data)
    parent = bpy.data.objects.new("PocketCam Smoke Parent", None)
    scene.collection.objects.link(parent)
    scene.collection.objects.link(camera)
    parent.location = Vector((5.0, 0.0, 0.0))
    camera.parent = parent
    camera.location = Vector((5.0, 0.0, 0.0))
    settings.camera = camera
    scene.camera = camera
    bpy.context.view_layer.update()

    identity_pose = {
        "type": "pose",
        "seq": 1,
        "position": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0, 1.0],
    }
    addon._state["pending_recenter"] = True
    addon._apply_pose(scene, settings, identity_pose)
    moved_pose = dict(identity_pose, seq=2, position=[1.0, 2.0, 3.0])
    addon._apply_pose(scene, settings, moved_pose)

    close(camera.matrix_world.translation.x, 11.0)
    close(camera.matrix_world.translation.y, 2.0)
    close(camera.matrix_world.translation.z, 3.0)
    close(camera.data.lens, 24.0)

    addon._start_recording(scene, settings)
    addon._state["record_start_clock"] = time.perf_counter() - 1.0
    recorded_pose = dict(identity_pose, seq=3, position=[2.0, 2.0, 3.0])
    addon._apply_pose(scene, settings, recorded_pose)
    addon._stop_recording(scene, settings)

    if camera.animation_data is None or camera.animation_data.action is None:
        raise AssertionError("Camera action was not created")
    if camera.data.animation_data is None or camera.data.animation_data.action is None:
        raise AssertionError("Lens action was not created")
    if scene.frame_end <= scene.frame_start:
        raise AssertionError("Recording did not extend the scene frame range")

    print("POCKETCAM_BLENDER_SMOKE_OK")
finally:
    addon.unregister()
