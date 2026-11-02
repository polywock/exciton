







import math
import typing as tp
from time import monotonic
import bpy
from ... import utils
from ... import windows
from .. import td
from . import confirm
from . import pointer
from . import screenshot
from . import watch

MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 1.0, 120.0, 30.0

AFTER_CLICK_SECONDS = 0.6

CHECK_SECONDS = 0.5
CLICKS = {"LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE"}


PREVIEW_SIDE = 1024


class SummonWaitForUser:
    def __init__(self, id: str, request: dict, on_resolve: tp.Callable[[td.SummonResponse], None]):
        self.id = id
        seconds = request.get("seconds")
        self.seconds = min(MAX_SECONDS, max(MIN_SECONDS, seconds)) if isinstance(seconds, (int, float)) else DEFAULT_SECONDS
        self.until_click = request.get("until") != "time"
        self.space = request.get("space")
        self.look = request.get("look") is not False
        self._on_resolve = on_resolve
        self._done = False
        self._started = monotonic()
        self._timers: list = []

    @classmethod
    def start(cls, msg: td.FromServerMessage, on_resolve: tp.Callable[[td.SummonResponse], None]) -> "SummonWaitForUser | None":
        id = msg.get("summon_id")
        request = msg.get("summon_request")
        if not id or not isinstance(request, dict):
            return None
        return cls(id, request, on_resolve)

    def run(self, is_active: tp.Callable[[], bool]):
        self._is_active = is_active
        if self.until_click:
            watch.add(self._hook_name, self._on_event)

            for window in windows.all_windows():
                watch.ensure(window)
        self._timers = [
            utils.set_timeout(self._time_up, self.seconds),
            utils.set_interval(self._check, CHECK_SECONDS),
        ]
        utils.logger.info("Waiting up to %gs%s", self.seconds, " for a click" if self.until_click else "")

    @property
    def _hook_name(self) -> str:
        return f"wait:{self.id}"

    def _on_event(self, window, event):
        if event.type not in CLICKS or event.value != "PRESS":
            return
        watch.remove(self._hook_name)

        utils.clear_timer(self._timers[0])
        where = _describe_click(window, event.mouse_x, event.mouse_y, self.space)
        after = monotonic() - self._started
        utils.set_timeout(lambda: self._finish(f"The user clicked after {_seconds(round(after))}{where}."), AFTER_CLICK_SECONDS)

    def _time_up(self):
        if self.until_click:
            self._finish(f"No click in {_seconds(self.seconds)}.")
        else:
            self._finish(f"Waited {_seconds(self.seconds)}.")

    def _check(self):
        if not self._is_active():
            self._finish(None)


    def _finish(self, result: str | None):
        if self._done:
            return
        self._done = True
        watch.remove(self._hook_name)
        for timer in self._timers:
            utils.clear_timer(timer)
        if result is None:
            return
        utils.logger.info("Wait done: %s", result)
        if not self.look:
            self._on_resolve({"status": "OK", "result": result, "logs": []})
        elif confirm.needs_asking([screenshot.PERMISSION]):
            self._on_resolve(
                {"status": "OK", "result": f"{result} No screenshot: the user hasn't allowed screenshots.", "logs": []}
            )
        else:

            screenshot.capture_later(windows.chat_window(), PREVIEW_SIDE, lambda reply: self._looked(result, reply))

    def _looked(self, result: str, reply: td.SummonResponse):
        if reply.get("status") != "OK":
            self._on_resolve({"status": "OK", "result": f"{result} {reply.get('error')}", "logs": []})
            return
        self._on_resolve({**reply, "result": result})




def _describe_click(window, x: float, y: float, space: tp.Any) -> str:
    on_pointer = ""

    p = pointer.recent()
    if p is not None and p.window == window:
        near = pointer.NEAR_PIXELS * bpy.context.preferences.system.ui_scale
        on_pointer = ", on the pointer" if math.hypot(x - p.x, y - p.y) <= near else ", not on the pointer"
    capture = screenshot.last_capture

    if capture is not None and capture.window == window and screenshot.capture_matches(capture):
        try:
            fx, fy = x / window.width, 1 - y / window.height
        except ReferenceError:
            return on_pointer
        if space == "normalized":
            sx, sy = fx * 1000, fy * 1000
        else:
            sx, sy = fx * capture.image_size[0], fy * capture.image_size[1]

        return f" at {sx:.0f},{sy:.0f} in the screenshot before this wait{on_pointer}"
    return f" in another Blender window{on_pointer}"


def _seconds(n: float) -> str:
    return f"{n:g} second{'' if n == 1 else 's'}"
