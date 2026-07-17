from __future__ import annotations

import json
import socket
import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = PROJECT_ROOT / "blender_addon"
sys.path.insert(0, str(ADDON_ROOT / "pocketcam_bridge"))

from server import PoseServer  # noqa: E402


class PoseServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = PoseServer(host="127.0.0.1", port=0)
        self.server.start()
        deadline = time.time() + 3.0
        while self.server.bound_port == 0 and time.time() < deadline:
            time.sleep(0.01)
        self.assertNotEqual(self.server.bound_port, 0)
        self.client = socket.create_connection(("127.0.0.1", self.server.bound_port), timeout=2.0)
        self.client.settimeout(2.0)

    def tearDown(self) -> None:
        try:
            self.client.close()
        finally:
            self.server.stop()

    def send(self, payload: dict) -> None:
        self.client.sendall(json.dumps(payload).encode("utf-8") + b"\n")

    def wait_for_event(self, kind: str, timeout: float = 2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for event in self.server.drain_events():
                if event.kind == kind:
                    return event
            time.sleep(0.01)
        self.fail(f"Timed out waiting for {kind!r}")

    def test_handshake_pose_coalescing_and_reply(self) -> None:
        self.wait_for_event("client_connected")
        self.send({"type": "hello", "protocol": 1, "client": "test"})
        hello = self.wait_for_event("hello")
        self.assertEqual(hello.payload["client"], "test")

        self.send(
            {
                "type": "pose",
                "seq": 1,
                "position": [0, 0, 0],
                "rotation": [0, 0, 0, 1],
            }
        )
        self.send(
            {
                "type": "pose",
                "seq": 2,
                "position": [1, 2, 3],
                "rotation": [0, 0, 0, 1],
            }
        )
        deadline = time.time() + 2.0
        first_pose = None
        while first_pose is None and time.time() < deadline:
            first_pose = self.server.pop_latest_pose()
            if first_pose is None:
                time.sleep(0.01)
        self.assertIsNotNone(first_pose)
        self.assertEqual(first_pose["seq"], 1)

        latest_pose = None
        while latest_pose is None and time.time() < deadline:
            latest_pose = self.server.pop_latest_pose()
            if latest_pose is None:
                time.sleep(0.01)
        self.assertIsNotNone(latest_pose)
        self.assertEqual(latest_pose["seq"], 2)

        self.assertTrue(self.server.send_json({"type": "status", "recording": False}))
        line = self.client.recv(4096).split(b"\n", 1)[0]
        reply = json.loads(line.decode("utf-8"))
        self.assertEqual(reply["type"], "status")

    def test_invalid_packet_reports_protocol_error(self) -> None:
        self.wait_for_event("client_connected")
        self.client.sendall(b"not-json\n")
        event = self.wait_for_event("protocol_error")
        self.assertIn("Invalid JSON", event.payload["message"])

    def test_preview_packet_is_sent_by_background_sender(self) -> None:
        self.wait_for_event("client_connected")
        self.assertTrue(
            self.server.send_preview(
                {
                    "type": "preview",
                    "seq": 7,
                    "width": 4,
                    "height": 2,
                    "format": "jpeg",
                    "data": "preview-bytes",
                }
            )
        )
        line = self.client.recv(4096).split(b"\n", 1)[0]
        reply = json.loads(line.decode("utf-8"))
        self.assertEqual(reply["type"], "preview")
        self.assertEqual(reply["seq"], 7)


if __name__ == "__main__":
    unittest.main()
