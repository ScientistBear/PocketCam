"""Low-latency camera viewport capture for PocketCam Bridge."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy
import gpu


@dataclass(frozen=True)
class PreviewFrame:
    jpeg: bytes
    width: int
    height: int


class PreviewCapture:
    """Render the selected camera through Blender's viewport and encode JPEG."""

    def __init__(self) -> None:
        self._offscreen: Any | None = None
        self._offscreen_size = (0, 0)
        self._image: bpy.types.Image | None = None
        self._image_size = (0, 0)
        self._filepath = Path(tempfile.gettempdir()) / f"pocketcam_preview_{os.getpid()}.jpg"
        self.last_error = ""

    def capture(
        self,
        scene: bpy.types.Scene,
        camera: bpy.types.Object,
        width: int,
    ) -> PreviewFrame | None:
        target = self._find_view3d(scene)
        if target is None:
            self.last_error = "Open a 3D View to stream the camera preview"
            return None
        window, view3d, region = target
        width, height = self._preview_size(scene, width)

        try:
            self._ensure_offscreen(width, height)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_camera = camera.evaluated_get(depsgraph)
            projection = evaluated_camera.calc_matrix_camera(
                depsgraph,
                x=width,
                y=height,
                scale_x=1.0,
                scale_y=1.0,
            )
            view_matrix = evaluated_camera.matrix_world.inverted_safe()
            view_layer = window.view_layer
            self._offscreen.draw_view3d(
                scene,
                view_layer,
                view3d,
                region,
                view_matrix,
                projection,
                do_color_management=True,
                draw_background=True,
            )
            pixels = gpu.types.Buffer("FLOAT", width * height * 4)
            with self._offscreen.bind():
                framebuffer = gpu.state.active_framebuffer_get()
                framebuffer.read_color(
                    0,
                    0,
                    width,
                    height,
                    4,
                    0,
                    "FLOAT",
                    data=pixels,
                )
            jpeg = self.encode_pixels(pixels, width, height)
            self.last_error = ""
            return PreviewFrame(jpeg=jpeg, width=width, height=height)
        except Exception as exc:
            self.last_error = f"Preview unavailable: {exc}"
            self._free_offscreen()
            return None

    def encode_pixels(self, pixels: Any, width: int, height: int) -> bytes:
        """Encode a Blender/GPU RGBA float buffer as JPEG."""

        self._ensure_image(width, height)
        assert self._image is not None
        self._image.pixels.foreach_set(pixels)
        self._image.update()
        self._image.filepath_raw = str(self._filepath)
        self._image.file_format = "JPEG"
        self._image.save()
        return self._filepath.read_bytes()

    def close(self) -> None:
        self._free_offscreen()
        image = self._image
        self._image = None
        self._image_size = (0, 0)
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except (ReferenceError, RuntimeError):
                pass
        try:
            self._filepath.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _preview_size(scene: bpy.types.Scene, requested_width: int) -> tuple[int, int]:
        width = max(160, min(640, int(requested_width)))
        render = scene.render
        denominator = max(1.0, float(render.resolution_y) * float(render.pixel_aspect_y))
        aspect = (float(render.resolution_x) * float(render.pixel_aspect_x)) / denominator
        height = int(round(width / max(0.25, min(4.0, aspect))))
        return width, max(120, min(640, height))

    @staticmethod
    def _find_view3d(
        scene: bpy.types.Scene,
    ) -> tuple[bpy.types.Window, bpy.types.SpaceView3D, bpy.types.Region] | None:
        fallback = None
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                region = next((item for item in area.regions if item.type == "WINDOW"), None)
                if region is None:
                    continue
                result = (window, area.spaces.active, region)
                if window.scene is scene:
                    return result
                fallback = fallback or result
        return fallback

    def _ensure_offscreen(self, width: int, height: int) -> None:
        if self._offscreen is not None and self._offscreen_size == (width, height):
            return
        self._free_offscreen()
        self._offscreen = gpu.types.GPUOffScreen(width, height, format="RGBA8")
        self._offscreen_size = (width, height)

    def _free_offscreen(self) -> None:
        offscreen = self._offscreen
        self._offscreen = None
        self._offscreen_size = (0, 0)
        if offscreen is not None:
            try:
                offscreen.free()
            except ReferenceError:
                pass

    def _ensure_image(self, width: int, height: int) -> None:
        if self._image is not None and self._image_size == (width, height):
            return
        if self._image is not None:
            try:
                bpy.data.images.remove(self._image)
            except (ReferenceError, RuntimeError):
                pass
        self._image = bpy.data.images.new(
            "PocketCam Preview Buffer",
            width=width,
            height=height,
            alpha=False,
            float_buffer=False,
        )
        self._image_size = (width, height)
