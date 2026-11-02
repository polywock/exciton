import typing as tp
from time import monotonic
from .. import types
from . import engine
from . import themes


GUIDE_SECONDS = 8.0
FLASH_SECONDS = 1.2


class _Shown(tp.NamedTuple):
    text: str
    until: float

    guide: bool




class CenterCaption:
    _shown: _Shown | None = None

    _area: types.FloatRect | None = None


    @classmethod
    def show_guide(cls, text: str, area: types.FloatRect | None):
        cls._area = area
        cls._shown = _Shown(text, monotonic() + GUIDE_SECONDS, guide=True)

    @classmethod
    def hide_guide(cls):
        if cls._shown and cls._shown.guide:
            cls._shown = None

    FLASH_SECONDS = FLASH_SECONDS


    @classmethod
    def flash(cls, text: str, seconds: float = FLASH_SECONDS):
        cls._shown = _Shown(text, monotonic() + seconds, guide=False)



    @classmethod
    def show(cls, text: str, seconds: float = FLASH_SECONDS, *, area: types.FloatRect | None):
        cls._area = area
        cls._shown = _Shown(text, monotonic() + seconds, guide=False)


    @classmethod
    def active(cls, now: float) -> bool:
        if cls._shown and cls._shown.until <= now:
            cls._shown = None
        return cls._shown is not None


    @classmethod
    def layout(cls, window: tp.Any) -> engine.CenterText | None:
        if not cls._shown:
            return None
        x, y, w, h = cls._area or (0, 0, window.width, window.height)

        style = themes.GUIDE if cls._shown.guide else themes.FLASH
        return engine.CenterText(cls._shown.text, (x + w / 2, window.height - (y + h / 2)), style)
