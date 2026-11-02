import json
import random
import websocket
from .. import configs
from .. import utils
from .. import registry as rg
from .. import types
from . import snapshot
from . import helpers




_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 30.0
_BACKOFF_MULTIPLIER = 2.0
_JITTER_MIN = 0.5

_QUIET_AFTER_ATTEMPTS = 30


_APP_PING = "ping"
_APP_PING_INTERVAL = 30.0

_CLOSE_REPLACED = 4000


class Channel:
    _ws: websocket.WebSocketApp | None = None
    _token: str | None = None
    _backoff: float = _BACKOFF_INITIAL
    _reconnect_timer: types.TimerCallback | None = None
    _reconnect_attempts: int = 0
    _ping_timer: types.TimerCallback | None = None



    _opened_before: bool = False

    @classmethod
    def connect(cls, token: str | None):
        if cls.is_open() and cls._token == token:
            return

        cls.disconnect()
        cls._token = token
        cls._backoff = _BACKOFF_INITIAL
        cls._reconnect_attempts = 0
        cls._opened_before = False
        cls._ping_timer = utils.set_interval(cls._send_app_ping, _APP_PING_INTERVAL)
        cls._connect()

    @classmethod
    def _connect(cls):
        if not cls._token:
            return

        if cls._ws:
            cls._ws.close()
        utils.logger.info("Channel connecting")
        cls._ws = websocket.WebSocketApp(
            helpers.ws_url("/channel-ws"),
            header={
                **helpers.auth_headers(cls._token),
                "X-Client-Id": utils.CLIENT_RUNTIME_ID,
                "X-Client-Label": utils.client_label(),
            },
            on_open=cls._on_open,
            on_message=cls._on_message,
            on_error=cls._on_error,
            on_close=cls._on_close,
        )
        utils.start_thread(cls._run_forever)

    @classmethod
    def _run_forever(cls):
        try:
            if cls._ws:


                cls._ws.run_forever(ping_interval=60, ping_timeout=10)
        except Exception:
            utils.logger.exception("Channel failed to run")

    @classmethod
    def disconnect(cls):
        cls._token = None
        if cls._reconnect_timer:
            utils.clear_timer(cls._reconnect_timer)
            cls._reconnect_timer = None
        if cls._ping_timer:
            utils.clear_timer(cls._ping_timer)
            cls._ping_timer = None
        if cls._ws:
            cls._ws.close()
            cls._ws = None

    @classmethod
    def _schedule_reconnect(cls):
        if not cls._token:
            return

        if cls._reconnect_timer:
            utils.clear_timer(cls._reconnect_timer)
        cls._reconnect_attempts += 1
        delay = cls._backoff * random.uniform(_JITTER_MIN, 1.0)
        cls._backoff = min(cls._backoff * _BACKOFF_MULTIPLIER, _BACKOFF_MAX)

        if cls._reconnect_attempts == _QUIET_AFTER_ATTEMPTS:
            utils.logger.warning(
                "Channel still offline after %d attempts; retrying every %d-%ds",
                cls._reconnect_attempts,
                _BACKOFF_MAX * _JITTER_MIN,
                _BACKOFF_MAX,
            )
        elif cls._reconnect_attempts < _QUIET_AFTER_ATTEMPTS:
            utils.logger.info("Channel reconnecting in %.1fs (attempt %d)", delay, cls._reconnect_attempts)
        cls._reconnect_timer = utils.set_timeout(cls._connect, delay)

    @classmethod
    def _on_open(cls, ws):
        if ws is not cls._ws:
            return
        utils.logger.info("Channel open")
        cls._backoff = _BACKOFF_INITIAL
        cls._reconnect_attempts = 0
        if cls._opened_before:


            utils.set_timeout(rg.Overlay.speed.clear)
            utils.set_timeout(snapshot.api_snapshot_rl)
        else:
            utils.set_timeout(cls._fetch_snapshot_if_missing)
        cls._opened_before = True


    @classmethod
    def _fetch_snapshot_if_missing(cls):
        if not configs.get_config().get("_active_snapshot"):
            utils.logger.info("Channel open without a snapshot: fetching it")
            snapshot.api_snapshot()

    @classmethod
    def _on_close(cls, ws, status_code, msg):


        if ws is not cls._ws:
            utils.logger.debug("Channel closed an old socket: %s %s", status_code, msg)
            return
        if status_code == _CLOSE_REPLACED:
            utils.logger.warning("Channel replaced by a newer connection from this Blender")
        else:
            utils.logger.info("Channel closed: %s %s", status_code, msg)
        cls._schedule_reconnect()

    @classmethod
    def _send_app_ping(cls):
        if not cls.is_open() or not cls._ws:
            return
        try:
            cls._ws.send(_APP_PING)
        except Exception as e:
            utils.logger.debug("Channel ping failed: %s: %s", type(e).__name__, e)

    @classmethod
    def _on_message(cls, ws, msg):
        if ws is not cls._ws:
            return
        if isinstance(msg, str):
            if msg == "pong":
                return
            data = json.loads(msg)
            utils.logger.debug("Channel message: %s", data.get("type"))
            if data.get("type") == "NO_AUTH":
                utils.logger.info("Channel rejected our token")


                def sign_out_if_current():
                    if ws is cls._ws:
                        rg.Overseer.sign_out()

                utils.set_timeout(sign_out_if_current)
            elif data.get("type") == "DIAGNOSTICS_REQUEST" and isinstance(data.get("requestId"), str):

                from . import diagnostics

                request_id = data["requestId"]
                utils.set_timeout(lambda: diagnostics.answer_request(request_id))
            elif data.get("type") == "SNAPSHOT_CHANGED":
                if data.get("clearSessionSpeed"):
                    utils.logger.info("Reading speed changed on the website: session speed cleared")
                    utils.set_timeout(rg.Overlay.speed.clear)
                utils.set_timeout(snapshot.api_snapshot_rl)

    @classmethod
    def _on_error(cls, ws, error):
        if helpers.is_normal_close(error):
            return
        utils.logger.warning("Channel error: %s: %s", type(error).__name__, error)

    @classmethod
    def is_open(cls) -> bool:
        return bool(cls._ws and cls._ws.sock and cls._ws.sock.connected)
