"""Exercise the actual TCP-to-Blender camera path with a simulated phone."""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "blender_addon"))

import pocketcam_bridge as addon  # noqa: E402
from pocketcam_bridge.server import PoseServer  # noqa: E402


def send(client: socket.socket, payload: dict) -> None:
    client.sendall(json.dumps(payload).encode("utf-8") + b"\n")


def pump_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        addon._timer_tick()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for Blender camera update")


addon.register()
client = None
server = PoseServer(host="127.0.0.1", port=0)
try:
    scene = bpy.context.scene
    settings = scene.pocketcam_settings
    settings.smoothing = 0.0
    settings.movement_scale = 1.0
    settings.preview_enabled = False

    camera_data = bpy.data.cameras.new("PocketCam Network Camera")
    camera = bpy.data.objects.new("PocketCam Network Camera", camera_data)
    scene.collection.objects.link(camera)
    settings.camera = camera

    addon._server = server
    server.start()
    deadline = time.time() + 3.0
    while server.bound_port == 0 and time.time() < deadline:
        time.sleep(0.01)
    client = socket.create_connection(("127.0.0.1", server.bound_port), timeout=2.0)

    identity = {
        "type": "pose",
        "seq": 1,
        "timestamp": 1.0,
        "position": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "tracking": "Tracking",
    }
    send(client, {"type": "hello", "protocol": 1, "client": "smoke-test"})
    send(client, identity)
    pump_until(lambda: addon._state["pose_packets"] >= 1)

    moved = dict(identity, seq=2, timestamp=2.0, position=[1.0, 2.0, 3.0])
    send(client, moved)
    pump_until(lambda: addon._state["last_pose_sequence"] == 2)

    location = camera.matrix_world.translation
    if any(abs(actual - expected) > 0.001 for actual, expected in zip(location, (1.0, 2.0, 3.0))):
        raise AssertionError(f"Camera did not follow TCP pose: {tuple(location)}")
    if scene.camera is not camera:
        raise AssertionError("PocketCam selection did not become the active scene camera")
    print("POCKETCAM_NETWORK_SMOKE_OK")
finally:
    if client is not None:
        client.close()
    server.stop()
    addon._server = None
    addon.unregister()
