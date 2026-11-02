import typing as tp
from .. import types

Align: tp.TypeAlias = tp.Literal["left", "center", "right"]

_DARK: types.ColorTuple = (0, 0, 0, 1)
_LIGHT: types.ColorTuple = (1, 0.95, 0.95, 1)



class Style(tp.NamedTuple):
    fill: types.ColorTuple = _DARK
    text: types.ColorTuple = _LIGHT
    stroke: types.ColorTuple = _LIGHT

    line_width: float = 1.0


    font_scale: float = 1.0

    padding: tuple[float, float, float, float] = (7.0, 10.0, 7.0, 10.0)

    rounding: float = 0.4

    line_spacing: float = 1.4
    min_width: float = 0.0

    max_width: float | None = None
    align: Align = "left"


LOADING = Style()
RECORDING = Style(fill=(0.6, 0, 0, 1))
TEXT = Style()

FINAL = TEXT

STATE_ON = Style(stroke=(0.35, 0.9, 0.55, 1), line_width=3.0)
STATE_OFF = Style(stroke=(1.0, 0.7, 0.3, 1), line_width=3.0)

TOOL = TEXT

GUIDE = Style(fill=(0.1, 0.1, 0.1, 1), stroke=(0.5, 0.5, 0.5, 1), rounding=0.1)

FLASH = Style(fill=(0.1, 0.1, 0.1, 1), stroke=(0.5, 0.5, 0.5, 1), rounding=0.1, align="center")
ERROR = Style(fill=(0.1, 0, 0, 1), text=(1, 0, 0, 1), stroke=(1, 0, 0, 1))

NOTICE = Style(text=(1, 0.8, 0.4, 1), stroke=(1, 0.8, 0.4, 1))
