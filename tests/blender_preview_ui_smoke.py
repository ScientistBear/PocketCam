"""Run in normal (non-background) Blender to exercise GPU viewport capture."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "blender_addon"))

from pocketcam_bridge.preview import PreviewCapture  # noqa: E402


result_path = Path(os.environ["POCKETCAM_UI_SMOKE_RESULT"])
capture = PreviewCapture()


def run_test() -> None:
    try:
        scene = bpy.context.scene
        camera = scene.camera
        if camera is None:
            raise AssertionError("Factory scene has no active camera")
        frame = capture.capture(scene, camera, 320)
        if frame is None:
            raise AssertionError(capture.last_error or "GPU capture returned no frame")
        if not frame.jpeg.startswith(b"\xff\xd8"):
            raise AssertionError("GPU preview was not encoded as JPEG")
        result_path.write_text(
            f"POCKETCAM_PREVIEW_UI_SMOKE_OK {frame.width}x{frame.height} {len(frame.jpeg)} bytes",
            encoding="utf-8",
        )
    except Exception:
        result_path.write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        capture.close()
        bpy.ops.wm.quit_blender()


bpy.app.timers.register(run_test, first_interval=1.0)
