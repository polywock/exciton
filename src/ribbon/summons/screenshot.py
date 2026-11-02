



import base64
import os
import shutil
import tempfile
import typing as tp
from dataclasses import dataclass
from time import monotonic
import bpy
from ... import utils
from ... import windows
from . import confirm
from .. import td

PERMISSION = "SEE_SCREEN"

MAX_SIDE = 1568
JPEG_QUALITY = 80

CAPTURE_DELAY_SECONDS = 0.25


HIDE_SECONDS = 0.15


capturing = False



@dataclass
class Capture:
    window: tp.Any

    window_size: tuple[int, int]
    image_size: tuple[int, int]
    at: float


last_capture: Capture | None = None




def capture_matches(capture: Capture) -> bool:
    if not windows.is_open(capture.window):
        return False
    return (capture.window.width, capture.window.height) == capture.window_size


class SummonScreenshot:
    def __init__(
        self,
        id: str,
        explanation: str,
        on_resolve: tp.Callable[[td.SummonResponse], None],
    ):
        self.id = id
        self.explanation = explanation
        self._on_resolve = on_resolve
        self._done = False

    @classmethod
    def start(cls, msg: td.FromServerMessage, on_resolve: tp.Callable[[td.SummonResponse], None]) -> "SummonScreenshot | None":
        id = msg.get("summon_id")
        request = msg.get("summon_request")
        if not id or not isinstance(request, dict):
            return None
        explanation = request.get("explanation")
        return cls(id, explanation if isinstance(explanation, str) else "", on_resolve)


    def run(self, is_active: tp.Callable[[], bool], on_waiting: tp.Callable[[], None]):
        if not confirm.needs_asking([PERMISSION]):
            utils.set_timeout(self._capture, 0)
            return
        if confirm.is_asking():
            self._reject(confirm.SCREENSHOT.busy)
            return
        on_waiting()
        confirm.ask(
            self.id,
            self.explanation,
            [PERMISSION],
            is_active,
            on_allow=lambda: utils.set_timeout(self._capture, CAPTURE_DELAY_SECONDS),
            on_reject=self._reject,
            kind=confirm.SCREENSHOT,
        )

    def _capture(self):
        capture_later(windows.chat_window(), MAX_SIDE, self._captured)

    def _captured(self, reply: td.SummonResponse):
        self._resolve(reply)

    def _reject(self, error: str):
        self._resolve({"status": "ERROR", "error": error, "logs": []})

    def _resolve(self, reply: td.SummonResponse):
        if self._done:
            return
        self._done = True
        self._on_resolve(reply)




def capture_later(window: tp.Any, max_side: int, on_done: tp.Callable[[td.SummonResponse], None]):
    global capturing
    if not windows.is_open(window):
        on_done({"status": "ERROR", "error": "Blender couldn't take a screenshot: the window was closed.", "logs": []})
        return
    capturing = True
    utils.redraw_all()

    def capture():
        global capturing
        try:
            if not windows.is_open(window):
                raise RuntimeError("the window was closed")
            data, size = capture_window(window, max_side)
        except Exception as e:
            utils.logger.warning("Screenshot failed", exc_info=True)
            on_done({"status": "ERROR", "error": f"Blender couldn't take a screenshot: {type(e).__name__}: {e}", "logs": []})
            return
        finally:
            capturing = False
            utils.redraw_all()
        utils.logger.info("Screenshot taken: %dx%d, %d bytes", size[0], size[1], len(data))
        on_done(
            {
                "status": "OK",
                "image": base64.b64encode(data).decode(),
                "media_type": "image/jpeg",
                "width": size[0],
                "height": size[1],
                "logs": [],
            }
        )

    utils.set_timeout(capture, HIDE_SECONDS)



def capture_window(window: tp.Any = None, max_side: int = MAX_SIDE) -> tuple[bytes, tuple[int, int]]:
    global last_capture
    window = window or next(iter(bpy.context.window_manager.windows), None)
    if window is None:
        raise RuntimeError("no window")
    folder = tempfile.mkdtemp(prefix="exciton-screenshot-")
    image = None
    try:
        raw = os.path.join(folder, "window.png")
        with bpy.context.temp_override(window=window, screen=window.screen):
            result = bpy.ops.screen.screenshot(filepath=raw, check_existing=False)
        if "FINISHED" not in result or not os.path.exists(raw):
            raise RuntimeError(f"screenshot operator returned {result}")
        image = bpy.data.images.load(raw, check_existing=False)
        width, height = image.size
        scale = min(1.0, max_side / max(width, height, 1))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        if scale < 1.0:
            image.scale(*size)
        out = os.path.join(folder, "window.jpg")
        image.filepath_raw = out
        image.file_format = "JPEG"
        image.save(filepath=out, quality=JPEG_QUALITY)
        with open(out, "rb") as f:
            data = f.read()
        last_capture = Capture(window, (width, height), size, monotonic())
        return data, size
    finally:

        if image is not None:
            bpy.data.images.remove(image)
        shutil.rmtree(folder, ignore_errors=True)
