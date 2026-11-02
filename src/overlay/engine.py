import functools
import typing as tp

from .. import utils
from .. import types
from . import painter
from . import themes
from ..ribbon import AnyJob as Job

DURATION_SHOW_ERROR = 5
MAX_WIDTH: float = 500.0


FONT_SIZE = 18.0


LEFT = 50.0
TOP_MARGIN = 14.0
GAP = 20.0





def column_top(window: tp.Any, drawable: tp.Container[str], ui_scale: float = 1.0) -> float:
    tops = [area.y + area.height for area in window.screen.areas if area.type in drawable]
    return window.height - max(tops, default=window.height) + TOP_MARGIN * ui_scale



def boxes(job: Job, now: float) -> list[tuple[str, themes.Style]]:
    display = job.display
    if display.hidden or display.dismissed:
        return []
    if job.state == "recording":
        shown = [(job.recording_label(now), themes.RECORDING) if job.recording_started else ("Loading", themes.LOADING)]

        if display.tool:
            shown.append((display.tool, themes.TOOL))
        return shown
    if job.state == "failed":
        if job.error_reason and utils.was_recent(job.resolved_at, DURATION_SHOW_ERROR, now):
            return [(job.error_reason, themes.NOTICE if job.error_kind == "notice" else themes.ERROR)]
        return []


    if display.final and display.shown_all():
        return []
    shown: list[tuple[str, themes.Style]] = []
    if display.current is not None:
        last = display.final and display.position + 1 >= len(display.texts)
        state = display.current.get("state")
        style = themes.FINAL if last else themes.TEXT
        if state is True:
            style = themes.STATE_ON
        elif state is False:
            style = themes.STATE_OFF
        shown.append((display.current["text"], style))

    if display.tool or display.current is None:
        shown.append((display.tool or "", themes.TOOL))
    return shown


def is_showing(job: Job, now: float) -> bool:
    return bool(boxes(job, now))


class Box(tp.NamedTuple):

    rect: types.FloatRect
    lines: tuple[str, ...]
    style: themes.Style



class CenterText(tp.NamedTuple):
    text: str
    middle: types.FloatPoint
    style: themes.Style







class Engine:
    def __init__(self, snapshot: types.Snapshot, ui_scale: float = 1.0):
        self.ui_scale = ui_scale
        self.scale = (snapshot.get("buiFontSize", None) or 1.0) * ui_scale
        self.max_width = (snapshot.get("buiMaxWidth", None) or MAX_WIDTH) * ui_scale
        self.boxes: list[Box] = []
        self._measurer = painter.Painter(0, (0.0, 0.0))


    def run(self, jobs: tp.Sequence[Job], now: float, top: float, center: CenterText | None = None):
        self.boxes = []
        y = top
        for job in jobs:
            for text, style in boxes(job, now):
                lines, (width, height) = self._measure(text, style)
                self.boxes.append(Box((LEFT * self.ui_scale, y, width, height), lines, style))
                y += height + GAP * self.ui_scale
        if center:
            lines, (width, height) = self._measure(center.text, center.style)
            x, y = center.middle
            self.boxes.append(Box((x - width / 2, y - height / 2, width, height), lines, center.style))

    def _measure(self, text: str, style: themes.Style) -> tuple[tuple[str, ...], tuple[float, float]]:
        self._measurer.font_size = self._font_size(style)
        lines = wrap(self._measurer.font_size, text, self._max_width(style))
        size = self._measurer.measure_multiline_text_box(
            lines, style.line_spacing, more_pads=self._padding(style), min_width=style.min_width * self.scale
        )
        return lines, size


    def draw(self, window_height: int, region: tp.Any):
        p = painter.Painter(window_height, (float(region.x), float(region.y)))
        for box in self.boxes:
            style = box.style
            p.font_size = self._font_size(style)
            p.fill_color = style.fill
            p.text_color = style.text
            p.stroke_color = style.stroke
            p.line_width = style.line_width * self.ui_scale
            p.draw_multiline_text_box(
                xy=box.rect[:2],
                lines=box.lines,
                line_spacing=style.line_spacing,
                rounding=style.rounding,
                more_pads=self._padding(style),
                min_width=style.min_width * self.scale,
                align=style.align,
            )

    def _font_size(self, style: themes.Style) -> float:
        return FONT_SIZE * style.font_scale * self.scale

    def _padding(self, style: themes.Style) -> tuple[float, float, float, float]:
        top, right, bottom, left = style.padding
        return (top * self.scale, right * self.scale, bottom * self.scale, left * self.scale)

    def _max_width(self, style: themes.Style) -> float:
        return style.max_width * self.scale if style.max_width is not None else self.max_width



@functools.lru_cache(maxsize=64)
def wrap(font_size: float, text: str, max_width: float) -> tuple[str, ...]:

    lines = [wrapped for line in text.split("\n") if line.strip() for wrapped in _wrap_line(font_size, line, max_width)]
    return tuple(lines) or (text,)


def _wrap_line(font_size: float, text: str, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if _width(font_size, candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word

        while len(current) > 1 and _width(font_size, current) > max_width:
            cut = _fitting_length(font_size, current, max_width)
            lines.append(current[:cut])
            current = current[cut:]
    if current:
        lines.append(current)
    return lines



def _fitting_length(font_size: float, text: str, max_width: float) -> int:
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _width(font_size, text[:middle]) <= max_width:
            low = middle
        else:
            high = middle - 1
    return low


def _width(font_size: float, text: str) -> float:
    return painter.Painter._get_text_dimensions(font_size, text)[0]
