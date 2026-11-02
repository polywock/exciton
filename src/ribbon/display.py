import typing as tp
import unicodedata
from .. import configs
from .. import utils



NOTICE_SECONDS = 1.0
CHARS_PER_SECOND = 15
MIN_SECONDS = 2.0
MAX_SECONDS = 10.0

REPLAY_DURATION_SCALE = 3.0


class ShownText(tp.TypedDict, total=False):
    text: tp.Required[str]

    time: tp.Required[float]
    duration_scale: float
    state: bool | None



class Display:
    def __init__(self):
        self.texts: list[str] = []

        self._states: dict[int, bool] = {}

        self.final = False
        self.tool: str | None = None

        self.hidden = False

        self.dismissed = False

        self.position = 0
        self.current: ShownText | None = None

    def add(self, text: str | None, final: bool, *, state: bool | None = None):
        if text:
            if state is not None:
                self._states[len(self.texts)] = state
            self.texts.append(text)
        self.final = final


    def dismiss(self):
        self.dismissed = True
        self.position = len(self.texts)
        self.current = None


    def shown_all(self) -> bool:
        return self.current is None and self.position >= len(self.texts)



    def on_screen(self) -> bool:
        return not self.hidden and not self.dismissed and not self.shown_all()



    def advance(self, now: float, speed: float):
        if self.hidden or self.dismissed:
            return
        if self.current is None:
            if self.position < len(self.texts):
                self.current = {"text": self.texts[self.position], "time": now, "state": self._states.get(self.position)}
            return
        if self.position + 1 >= len(self.texts) and not self.final:
            return
        duration = reading_seconds(self.current["text"]) * self.current.get("duration_scale", 1.0) / speed
        if utils.was_recent(self.current["time"], duration, now):
            return
        self.position += 1
        self.current = None


    def replay(self, step: int, now: float) -> bool:
        return self._step(step, now, REPLAY_DURATION_SCALE)


    def move_on(self, now: float) -> bool:
        return self._step(1, now, 1.0)



    def _step(self, step: int, now: float, duration_scale: float) -> bool:
        index = self.position + step
        if step > 0 and index == len(self.texts) and self.current is not None:
            self.position = index
            self.current = None
            return True
        if not 0 <= index < len(self.texts):
            return False
        self.position = index
        self.current = {
            "text": self.texts[index],
            "time": now,
            "duration_scale": duration_scale,
            "state": self._states.get(index),
        }
        self.dismissed = False
        return True




class ReadingSpeed:
    STEP = 0.25

    MIN = 0.25
    MAX = 4.0
    _session: float | None = None

    @classmethod
    def current(cls) -> float:
        return max(cls.MIN, cls._session or cls._website())



    @classmethod
    def clear(cls):
        cls._session = None


    @classmethod
    def change(cls, step: int) -> float:
        steps = round((cls.current() + step * cls.STEP) / cls.STEP)
        cls._session = min(cls.MAX, max(cls.MIN, steps * cls.STEP))
        return cls._session

    @classmethod
    def _website(cls) -> float:
        snapshot = configs.get_config().get("_active_snapshot") or {}
        return snapshot.get("buiSpeed", None) or 1.0



def reading_seconds(text: str) -> float:
    weight = sum(2.5 if _is_cjk(c) else 1.0 for c in text if not c.isspace())
    return min(MAX_SECONDS, max(MIN_SECONDS, NOTICE_SECONDS + weight / CHARS_PER_SECOND))


def _is_cjk(char: str) -> bool:
    return "CJK" in unicodedata.name(char, "")
