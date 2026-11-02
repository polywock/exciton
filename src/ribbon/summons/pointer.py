







import math
import typing as tp
from dataclasses import dataclass
from time import monotonic
import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from ... import utils
from ... import windows
from .. import td
from . import screenshot
from . import watch

STYLES = ("ring", "arrow", "dot")
MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 1.0, 60.0, 8.0

NEAR_AFTER_SECONDS = 1.5
NEAR_PIXELS = 40

CAPTURE_MAX_AGE_SECONDS = 10 * 60
BLINK_SECONDS = 1.0
MAX_LABEL_CHARS = 40

COLOR = (1.0, 0.8, 0.15)
OUTLINE = (0.05, 0.05, 0.05)


@dataclass
class Pointer:
    window: tp.Any

    x: float
    y: float
    style: str
    label: str
    shown_at: float
    until: float

    direction: tp.Literal["up", "down"] = "up"

    armed: bool = False


current: Pointer | None = None

_last: tuple[Pointer, float] | None = None

RECENT_SECONDS = 10.0


class SummonPoint:
    def __init__(self, request: dict, on_resolve: tp.Callable[[td.SummonResponse], None]):
        self.request = request
        self._on_resolve = on_resolve

    @classmethod
    def start(cls, msg: td.FromServerMessage, on_resolve: tp.Callable[[td.SummonResponse], None]) -> "SummonPoint | None":
        request = msg.get("summon_request")
        if not msg.get("summon_id") or not isinstance(request, dict):
            return None
        return cls(request, on_resolve)

    def run(self):
        try:
            result = point(self.request)
        except PointError as e:
            self._on_resolve({"status": "ERROR", "error": str(e), "logs": []})
            return
        except Exception as e:
            utils.logger.warning("Pointing failed", exc_info=True)
            self._on_resolve({"status": "ERROR", "error": f"Blender couldn't point there: {type(e).__name__}: {e}", "logs": []})
            return
        self._on_resolve({"status": "OK", "result": result, "logs": []})


class PointError(Exception):
    pass



def point(request: dict) -> str:
    global current
    x, y = request.get("x"), request.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise PointError("x and y must be numbers.")
    capture = screenshot.last_capture
    if capture is None or monotonic() - capture.at > CAPTURE_MAX_AGE_SECONDS:
        raise PointError("Take a screenshot first: points are in the latest screenshot's coordinates.")

    if not windows.is_open(capture.window) or capture.window != windows.chat_window():
        raise PointError("The latest screenshot isn't of the window the user is in now. Take a new screenshot.")
    if not screenshot.capture_matches(capture):
        raise PointError("The window was resized since the latest screenshot, which moves its controls. Take a new screenshot.")
    width, height = capture.window.width, capture.window.height


    if request.get("space") == "normalized":
        fx, fy = x / 1000, y / 1000
    else:
        fx, fy = x / capture.image_size[0], y / capture.image_size[1]
    if not (0 <= fx <= 1 and 0 <= fy <= 1):
        raise PointError(f"{x},{y} is outside the screenshot.")
    wx, wy = fx * width, (1 - fy) * height

    style = request.get("style") if request.get("style") in STYLES else "ring"
    label = request.get("label") if isinstance(request.get("label"), str) else ""
    label = " ".join(label.split())[:MAX_LABEL_CHARS]
    seconds = request.get("seconds")
    seconds = min(MAX_SECONDS, max(MIN_SECONDS, seconds)) if isinstance(seconds, (int, float)) else DEFAULT_SECONDS

    note = ""
    direction: tp.Literal["up", "down"] = "up"


    areas = capture.window.screen.areas
    if areas and not any(a.x <= wx < a.x + a.width and a.y <= wy < a.y + a.height for a in areas):
        top = max(a.y + a.height for a in areas)
        bottom = min(a.y for a in areas)
        if wy >= top:
            wy, direction, style = top - 2, "up", "arrow"
        elif wy < bottom:
            wy, direction, style = bottom + 2, "down", "arrow"
        if style == "arrow":
            note = " Blender's bars can't be drawn in, so an arrow points at it from the editor next to it."

    now = monotonic()
    current = Pointer(capture.window, wx, wy, style, label, now, now + seconds, direction)
    watch.add("pointer", _on_event)

    watch.ensure(capture.window)
    current.armed = not _cursor_near(current)
    utils.redraw_all()
    utils.logger.info("Pointing at %.0f,%.0f (%s, %.0fs): %s", wx, wy, style, seconds, label)
    article = "an" if style == "arrow" else "a"
    return f"Pointing at it with {article} {style} for {seconds:g} seconds, or until the user's cursor reaches it.{note}"


def clear():
    global current, _last
    watch.remove("pointer")
    if current is not None:
        _last = (current, monotonic())
        current = None
        utils.redraw_all()



def recent() -> Pointer | None:
    if current is not None:
        return current
    if _last is not None and monotonic() - _last[1] <= RECENT_SECONDS:
        return _last[0]
    return None



def active(now: float) -> Pointer | None:
    if current is not None and (now >= current.until or not windows.is_open(current.window)):
        clear()
    return current



def extent(p: Pointer) -> tuple[float, float, float, float]:
    s = bpy.context.preferences.system.ui_scale
    reach = 40 * s + (len(p.label) * 9 * s if p.label else 0)
    return p.x - 40 * s, p.y - 40 * s, p.x + reach, p.y + 40 * s





def draw(p: Pointer, region, now: float):
    s = bpy.context.preferences.system.ui_scale
    x, y = p.x - region.x, p.y - region.y

    phase = 0.5 + 0.5 * math.cos((now - p.shown_at) / BLINK_SECONDS * 2 * math.pi)
    alpha = 0.35 + 0.65 * phase
    gpu.state.blend_set("ALPHA")
    if p.style == "dot":
        _disc(x, y, 9 * s, (*OUTLINE, 0.8 * alpha))
        _disc(x, y, 7 * s, (*COLOR, alpha))
    elif p.style == "arrow":
        _arrow(x, y, s, p.direction, alpha)
    else:
        radius = (16 + 3 * phase) * s
        _ring(x, y, radius + 1.5 * s, 6 * s, (*OUTLINE, 0.7 * alpha))
        _ring(x, y, radius, 3 * s, (*COLOR, alpha))
    if p.label:
        _label(x + 22 * s, y - 28 * s if p.direction == "up" else y + 22 * s, p.label, s, alpha)
    gpu.state.blend_set("NONE")


def _shader():
    return gpu.shader.from_builtin("UNIFORM_COLOR")


def _tris(points: list[tuple[float, float]], indices: list[tuple[int, int, int]], color):
    shader = _shader()
    batch = batch_for_shader(shader, "TRIS", {"pos": points}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def _disc(x, y, r, color, segments=32):
    points = [(x, y)] + [
        (x + math.cos(i / segments * math.tau) * r, y + math.sin(i / segments * math.tau) * r) for i in range(segments)
    ]
    _tris(points, [(0, 1 + i, 1 + (i + 1) % segments) for i in range(segments)], color)


def _ring(x, y, r, thickness, color, segments=48):
    points = []
    for i in range(segments):
        a = i / segments * math.tau
        points += [
            (x + math.cos(a) * r, y + math.sin(a) * r),
            (x + math.cos(a) * (r - thickness), y + math.sin(a) * (r - thickness)),
        ]
    indices = []
    for i in range(segments):
        o, n = 2 * i, 2 * ((i + 1) % segments)
        indices += [(o, o + 1, n), (n, o + 1, n + 1)]
    _tris(points, indices, color)



_ARROW = [(0, 0), (0, -22), (5, -17), (9, -26), (13, -24), (9, -15), (16, -15)]
_ARROW_TRIS = [(0, 1, 2), (0, 2, 5), (0, 5, 6), (2, 3, 4), (2, 4, 5)]


def _arrow(x, y, s, direction, alpha):
    flip = -1 if direction == "down" else 1
    for scale, color in ((1.35, (*OUTLINE, 0.8 * alpha)), (1.0, (*COLOR, alpha))):

        nudge = (-2 * s, 3 * s * flip) if scale > 1 else (0, 0)
        points = [(x + nudge[0] + px * s * scale, y + nudge[1] + py * s * scale * flip) for px, py in _ARROW]
        _tris(points, _ARROW_TRIS, color)


def _label(x, y, text, s, alpha):
    font = 0
    blf.size(font, 13 * s)
    w, h = blf.dimensions(font, text)
    pad = 5 * s
    _tris(
        [(x - pad, y - pad), (x + w + pad, y - pad), (x + w + pad, y + h + pad), (x - pad, y + h + pad)],
        [(0, 1, 2), (0, 2, 3)],
        (*OUTLINE, 0.85 * max(alpha, 0.6)),
    )
    blf.color(font, *COLOR, 1.0)
    blf.position(font, x, y, 0)
    blf.draw(font, text)






def _cursor_near(p: Pointer) -> bool:
    if watch.cursor is None or watch.cursor[0] != p.window:
        return False
    near = NEAR_PIXELS * bpy.context.preferences.system.ui_scale
    return math.hypot(watch.cursor[1] - p.x, watch.cursor[2] - p.y) <= near


def _on_event(window, event):
    p = active(monotonic())
    if p is None or event.type != "MOUSEMOVE" or window != p.window:
        return
    if not _cursor_near(p):
        p.armed = True
    elif p.armed and monotonic() - p.shown_at >= NEAR_AFTER_SECONDS:
        utils.logger.info("Pointer reached by the cursor")
        clear()


def unregister():
    clear()
