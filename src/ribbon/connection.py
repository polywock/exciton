









import base64
import collections
import json
import queue
import threading
import time
import typing as tp
from time import monotonic
import websocket

from .. import configs
from .. import types
from .. import utils
from ..api import helpers as api_helpers
from . import td


AUDIO_PREFIX = "AUDIO::"
AUDIO_END = "AUDIO-END::"


_STANDBY_WAIT_SECONDS = 5.0


_OPEN_SECONDS = 10.0



_PING_SECONDS = 15
_PING_TIMEOUT_SECONDS = 5



_KEEPALIVE_SECONDS = 15


class RibbonConnection:
    def __init__(self, token: str | None):

        self.token = token
        self.created_at = monotonic()
        self.opened_at: float | None = None

        self.closed_at: float | None = None


        self.kind: tp.Literal["SPARE", "OPENING", "NEW"] = "NEW"
        self.how = "a new one"


        self.colo: str | None = None
        self.edge_rtt_ms: int | None = None


        self.rtt_noted = False
        self.shop_tries = 0


        self.uses = 0
        self._standby = False
        self._released = False

        self._label = "Spare connection"
        self._is_active: tp.Callable[[], bool] = lambda: False
        self._on_open: tp.Callable[[], None] = lambda: None
        self._on_message: tp.Callable[[td.FromServerMessage], None] = lambda _msg: None
        self._on_close: tp.Callable[[], None] = lambda: None
        self._on_audio: tp.Callable[[bytes], None] | None = None
        self._attached = False
        self._open = False
        self._closed = False

        self._close_reported = False

        self._opened_wall = 0.0
        self._kept_alive_at = 0.0
        self._ws: websocket.WebSocketApp | None = None


        self._lock = threading.Lock()
        utils.start_thread(self._run)
        utils.set_timeout(self._open_expired, _OPEN_SECONDS)



    def attach(
        self,

        label: str,

        is_active: tp.Callable[[], bool],

        on_open: tp.Callable[[], None],

        on_message: tp.Callable[[td.FromServerMessage], None],

        on_close: tp.Callable[[], None],

        on_audio: tp.Callable[[bytes], None] | None = None,
    ):
        with self._lock:
            self._label, self._is_active = label, is_active
            self._on_open, self._on_message, self._on_close, self._on_audio = on_open, on_message, on_close, on_audio
            self._attached = True
            self._standby = self._released = False
            self.uses += 1
            closed, start = self._closed, self._open
        if closed:
            utils.set_timeout(self._on_close, 0)
        elif start:
            self._start()



    def release(self):
        with self._lock:
            self._label = "Spare connection"
            self._is_active = lambda: False
            self._on_open, self._on_close, self._on_audio = (lambda: None), (lambda: None), None
            self._on_message = lambda _msg: None
            self._attached = False
            self._released = True
            standby = self._standby
        if standby:
            Spare.reuse(self)
        else:
            uses = self.uses
            utils.set_timeout(lambda: self._release_expired(uses), _STANDBY_WAIT_SECONDS)



    def _release_expired(self, uses: int):
        with self._lock:
            expired = self._released and not self._standby and self.uses == uses
        if expired:
            self.close()

    def is_open(self) -> bool:
        return self._open and not self._closed

    def is_closed(self) -> bool:
        return self._closed


    def is_fresh(self) -> bool:
        ws = self._ws
        if not self.is_open() or not ws:
            return False

        heard = max(self._opened_wall + _PING_SECONDS, ws.last_pong_tm)
        return time.time() - heard < _PING_SECONDS + _PING_TIMEOUT_SECONDS + 5




    def rtt_ms(self) -> int | None:
        ws = self._ws
        if not ws or not ws.last_pong_tm or ws.last_pong_tm < ws.last_ping_tm:
            return None
        return round((ws.last_pong_tm - ws.last_ping_tm) * 1000)


    def keep_alive(self):
        now = monotonic()
        with self._lock:
            due = self._open and not self._closed and not self._attached and now - self._kept_alive_at >= _KEEPALIVE_SECONDS
            if due:
                self._kept_alive_at = now
                self.send_json({"type": "KEEPALIVE"})

    def send_json(self, data: td.FromClientMessage) -> bool:
        return self._send(json.dumps(data))



    def stream_audio(self, chunks: "queue.Queue[bytes | object]", end: object, on_end: tp.Callable[[], None] | None = None):
        def run():
            while not self._closed:
                data = chunks.get()
                if data is end:
                    if on_end:
                        on_end()
                    self._send(AUDIO_END)
                    return
                if isinstance(data, bytes) and not self._send(AUDIO_PREFIX + base64.b64encode(data).decode()):
                    return

        utils.start_thread(run)





    def close(self):
        with self._lock:
            self._closed = True
            ws = self._ws
        if ws:
            utils.start_thread(ws.close)

    def _run(self):
        with self._lock:
            if self._closed:
                return
            ws = self._ws = websocket.WebSocketApp(
                api_helpers.ws_url("/ribbon-ws"),
                header=api_helpers.auth_headers(self.token),
                on_open=self._opened,
                on_message=self._receive,
                on_error=self._error,
                on_close=self._close,
            )
        ws.run_forever(ping_interval=_PING_SECONDS, ping_timeout=_PING_TIMEOUT_SECONDS, skip_utf8_validation=False)



    def _open_expired(self):
        with self._lock:
            expired = not self._open and not self._closed
        if expired:
            utils.logger.warning("%s didn't open within %.0fs", self._label, _OPEN_SECONDS)
            self.close()
            self._close(None, None, "didn't open in time")

    def _opened(self, ws: websocket.WebSocketApp):
        with self._lock:
            closed = self._closed
            self._open = True
            self.opened_at = monotonic()
            self._opened_wall = time.time()
            start = self._attached
        if closed:
            ws.close()
        elif start:
            self._start()

    def _start(self):
        self._on_open()
        self.send_json({"type": "START"})

    def _send(self, text: str) -> bool:
        ws = self._ws
        if not ws or self._closed:
            return False
        try:
            ws.send(text, websocket.ABNF.OPCODE_TEXT)
            return True
        except Exception:
            utils.logger.info("%s couldn't send %s", self._label, text[:16], exc_info=True)
            return False

    def _receive(self, _ws, text: str | bytes):
        if not isinstance(text, str):
            return
        if text.startswith(AUDIO_PREFIX):
            if self._on_audio and self._is_active():
                self._on_audio(base64.b64decode(text[len(AUDIO_PREFIX) :]))
            return
        msg: td.FromServerMessage = json.loads(text)

        if msg.get("type") == "EDGE":
            self.colo, self.edge_rtt_ms = msg.get("colo"), msg.get("rtt_ms")
            return
        if msg.get("type") == "STANDBY":
            with self._lock:
                self._standby = True
                released = self._released
            if released:
                utils.set_timeout(lambda: Spare.reuse(self), 0)
            return
        if not self._is_active():
            return

        msg["received_at"] = monotonic()
        on_message = self._on_message
        utils.set_timeout(lambda: on_message(msg), 0)

    def _error(self, _ws, error):
        if api_helpers.is_normal_close(error):
            return
        utils.logger.warning("%s socket error: %s: %s", self._label, type(error).__name__, error)

    def _close(self, _ws, status_code, reason):
        with self._lock:
            if self._close_reported:
                return
            self._closed = self._close_reported = True
            self.closed_at = monotonic()
            attached = self._attached
        if not attached:
            return



        def closed():
            if self._is_active():
                utils.logger.warning("%s socket closed early: %s %s", self._label, status_code, reason)
            self._on_close()

        utils.set_timeout(closed, 0)



def connect(
    label: str,
    is_active: tp.Callable[[], bool],
    on_open: tp.Callable[[], None],
    on_message: tp.Callable[[td.FromServerMessage], None],
    on_close: tp.Callable[[], None],
    on_audio: tp.Callable[[bytes], None] | None = None,
) -> RibbonConnection:
    token = configs.get_config().get("token")
    connection = Spare.take(token)
    if connection and connection.opened_at is not None:
        connection.kind, connection.how = "SPARE", f"the spare, open {monotonic() - connection.opened_at:.0f}s"
    elif connection:
        connection.kind, connection.how = "OPENING", "the spare, still opening"
    else:
        connection = RibbonConnection(token)
        connection.how = f"a new one ({Spare.missed})"
    if connection.edge_rtt_ms is not None:
        connection.how += f", via {connection.colo} {connection.edge_rtt_ms} ms"
    if connection.uses:
        connection.how += f", reused after {connection.uses} job{'s' if connection.uses > 1 else ''}"
    utils.logger.debug("%s uses %s", label, connection.how)
    connection.attach(label, is_active, on_open, on_message, on_close, on_audio)
    return connection



_SPARE_TICK_SECONDS = 5.0


SPARE_ROTATE_SECONDS = 240
_SPARE_HOLD_SECONDS = SPARE_ROTATE_SECONDS + 60


_OUT_SECONDS = 30.0


_SPARE_IDLE_SECONDS = 60 * 60














_GOOD_FACTOR = 1.3
_GOOD_EXTRA_MS = 10
_FAR_FACTOR = 2
_FAR_EXTRA_MS = 40
_BETTER_MS = 10
_RECENT_RTTS = 10
_SHOP_TRIES = 3
_TUNE_TRIES = 2
_SHOP_WAIT_SECONDS = 5.0

_SPARE_SHORT_LIVED_SECONDS = 10
_SPARE_BACKOFF_INITIAL = 2.0
_SPARE_BACKOFF_MAX = 60.0






class Spare:
    _token: str | None = None
    _ready: RibbonConnection | None = None

    _next: RibbonConnection | None = None

    _candidate: RibbonConnection | None = None

    _out: RibbonConnection | None = None
    _out_since = 0.0

    _recent_rtts: tp.ClassVar["collections.deque[int]"] = collections.deque(maxlen=_RECENT_RTTS)
    _wanted_until = 0.0
    _retry_at = 0.0
    _backoff = _SPARE_BACKOFF_INITIAL
    _timer: types.TimerCallback | None = None

    missed = ""


    @classmethod
    def keep(cls, token: str | None):
        if token == cls._token:
            return
        cls._close_all()
        utils.clear_timer(cls._timer)
        cls._timer = None
        cls._token = token
        cls._backoff = _SPARE_BACKOFF_INITIAL
        cls._retry_at = 0.0
        if token:
            cls._wanted_until = monotonic() + _SPARE_IDLE_SECONDS
            cls._timer = utils.set_interval(cls._tick, _SPARE_TICK_SECONDS)
            cls._tick()


    @classmethod
    def take(cls, token: str | None) -> RibbonConnection | None:
        cls._wanted_until = monotonic() + _SPARE_IDLE_SECONDS
        if not cls._token:
            cls.missed = "no spare kept"
            return None

        cls._tick()
        spare = cls._ready
        if spare is not None and spare.token == token and spare.is_fresh():
            cls._ready = None
        elif cls._next is not None and cls._next.token == token and not cls._next.is_closed():

            spare, cls._next = cls._next, None
        else:
            other = spare or cls._next
            cls.missed = "spare for an older sign-in" if other and other.token != token else "spare failing to connect"
            return None
        cls._out, cls._out_since = spare, monotonic()
        cls._tick()
        return spare





    @classmethod
    def reuse(cls, connection: RibbonConnection):
        now = monotonic()
        age = now - (connection.opened_at or now)
        if (
            not cls._token
            or connection.token != cls._token
            or not connection.is_fresh()
            or age > SPARE_ROTATE_SECONDS
            or cls._far(connection)
        ):
            connection.close()
            return
        cls._wanted_until = now + _SPARE_IDLE_SECONDS
        if connection is cls._out:
            cls._out = None
        ready, upcoming = cls._ready, cls._next
        cls._ready = connection
        if ready is not None:
            if upcoming is not None:
                upcoming.close()
            cls._next = ready

    @classmethod
    def _tick(cls):
        now = monotonic()
        if not cls._token or now > cls._wanted_until:
            cls._close_all()
            return
        for slot in ("_ready", "_next"):
            connection: RibbonConnection | None = getattr(cls, slot)
            if connection and connection.is_closed():
                lasted = (connection.closed_at or now) - (connection.opened_at or now)
                if connection.opened_at is None or lasted < _SPARE_SHORT_LIVED_SECONDS:
                    cls._retry_at = now + cls._backoff
                    cls._backoff = min(cls._backoff * 2, _SPARE_BACKOFF_MAX)
                setattr(cls, slot, None)

        cls._shop(now)
        ready = cls._ready
        age = now - (ready.opened_at or now) if ready else 0.0
        stale = ready is None or not ready.is_fresh() or age > SPARE_ROTATE_SECONDS

        upcoming = cls._next
        holding = (
            ready is not None
            and ready.is_fresh()
            and age <= _SPARE_HOLD_SECONDS
            and not cls._far(ready)
            and upcoming is not None
            and cls._far(upcoming)
            and (cls._candidate is not None or upcoming.shop_tries < _SHOP_TRIES)
        )

        if stale and not holding and cls._next and cls._next.is_open():
            cls._ready, cls._next = cls._next, None
            if ready:
                ready.close()
        for spare in (cls._ready, cls._next):
            if spare and spare.is_open():
                spare.keep_alive()


        upcoming = cls._next
        old = upcoming is not None and now - (upcoming.opened_at or now) > SPARE_ROTATE_SECONDS and cls._candidate is None
        if upcoming and upcoming.is_open() and (not upcoming.is_fresh() or old):
            cls._next.close()
            cls._next = None
        out = cls._out
        if out and (out.is_closed() or now - cls._out_since > _OUT_SECONDS):
            cls._out = out = None

        if cls._next is None and now >= cls._retry_at and not (out and cls._ready and cls._ready.is_fresh()):
            cls._next = RibbonConnection(cls._token)
        cls._shop(now)

        if ready and ready.opened_at is not None and now - ready.opened_at >= _SPARE_SHORT_LIVED_SECONDS:
            cls._backoff = _SPARE_BACKOFF_INITIAL


    @classmethod
    def _shop(cls, now: float):
        for connection in (cls._ready, cls._next, cls._candidate):
            if connection and connection.edge_rtt_ms is not None and not connection.rtt_noted:
                connection.rtt_noted = True
                cls._recent_rtts.append(connection.edge_rtt_ms)
        ready, upcoming = cls._ready, cls._next

        if ready and upcoming and upcoming.is_fresh() and not cls._good(ready) and cls._better(upcoming, ready):
            cls._ready, cls._next = upcoming, ready
        candidate = cls._candidate
        if candidate and (candidate.is_closed() or not (cls._next and cls._tries_for(cls._next))):

            candidate.close()
            cls._candidate = candidate = None
        if candidate and candidate.edge_rtt_ms is not None:
            cls._candidate = None
            if cls._better(candidate, cls._next):
                cls._next.close()
                cls._next = candidate
            else:
                candidate.close()
            return
        if candidate and candidate.opened_at is None and now - candidate.created_at > _SHOP_WAIT_SECONDS:

            candidate.close()
            cls._candidate = None
            return
        if candidate and candidate.opened_at is not None and now - candidate.opened_at > _SHOP_WAIT_SECONDS:

            candidate.close()
            cls._candidate = None
            cls._next.shop_tries = _SHOP_TRIES
            return
        upcoming = cls._next
        if candidate is None and upcoming and upcoming.is_open() and upcoming.shop_tries < cls._tries_for(upcoming):
            upcoming.shop_tries += 1
            cls._candidate = RibbonConnection(cls._token)

    @classmethod
    def _best(cls) -> int | None:
        return min(cls._recent_rtts) if cls._recent_rtts else None

    @classmethod
    def _far(cls, connection: RibbonConnection) -> bool:
        rtt, best = connection.edge_rtt_ms, cls._best()
        return rtt is not None and best is not None and rtt > max(best * _FAR_FACTOR, best + _FAR_EXTRA_MS)


    @classmethod
    def _good(cls, connection: RibbonConnection) -> bool:
        rtt, best = connection.edge_rtt_ms, cls._best()
        return rtt is None or best is None or rtt <= max(best * _GOOD_FACTOR, best + _GOOD_EXTRA_MS)


    @classmethod
    def _tries_for(cls, connection: RibbonConnection) -> int:
        return _SHOP_TRIES if cls._far(connection) else 0 if cls._good(connection) else _TUNE_TRIES


    @classmethod
    def _better(cls, a: RibbonConnection, b: RibbonConnection) -> bool:
        if a.edge_rtt_ms is None or b.edge_rtt_ms is None or a.edge_rtt_ms >= b.edge_rtt_ms:
            return False
        return cls._good(a) or a.edge_rtt_ms <= b.edge_rtt_ms - _BETTER_MS

    @classmethod
    def _close_all(cls):
        for connection in (cls._ready, cls._next, cls._candidate):
            if connection:
                connection.close()
        cls._ready = cls._next = cls._candidate = cls._out = None
