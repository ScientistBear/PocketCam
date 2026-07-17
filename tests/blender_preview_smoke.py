"""Verify Blender can encode the GPU-style RGBA preview buffer as JPEG."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "blender_addon"))

from pocketcam_bridge.preview import PreviewCapture  # noqa: E402


width, height = 32, 18
pixel = [0.08, 0.35, 0.8, 1.0]
buffer = pixel * (width * height)
capture = PreviewCapture()
try:
    jpeg = capture.encode_pixels(buffer, width, height)
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise AssertionError("Preview output is not a complete JPEG")
    if len(jpeg) < 200:
        raise AssertionError("Preview JPEG was unexpectedly small")
    print(f"POCKETCAM_PREVIEW_SMOKE_OK {len(jpeg)} bytes")
finally:
    capture.close()
