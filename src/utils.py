import typing as tp
from time import monotonic
import threading
import logging
import logging.handlers
import tomllib
import bpy
import os
import sys
import uuid
import platform
import pathlib
from . import types




IS_RELEASE_BUILD = True
IS_DEBUG = bpy.app.debug
IS_DEV = IS_DEBUG and not IS_RELEASE_BUILD
WEB_APP_URL = "http://localhost:3000"

FORCE_NO_PORTAUDIO: tp.Literal["linux", "other"] | None = None

FORCE_UPDATE_REQUIRED = False


if not IS_DEV:
    FORCE_NO_PORTAUDIO = None
    FORCE_UPDATE_REQUIRED = False
    WEB_APP_URL = "https://exciton.dev"


logger = logging.getLogger("exciton")
LOG_MAX_BYTES = 1024 * 1024
_LOG_BACKUPS = 2
_file_handler: logging.Handler | None = None
LOG_PATH: str | None = None


def allows_internet():
    return bpy.context.preferences.system.use_online_access


_timer_callbacks: set[types.TimerCallback] = set()


def register_timer(cb: types.TimerCallback, first_interval: float, persistent=True) -> types.TimerCallback:
    def wrapper():
        try:
            result = cb()
        except Exception:

            logger.exception("Timer callback failed")
            result = None
        if not result:
            _timer_callbacks.discard(wrapper)
        return result

    _timer_callbacks.add(wrapper)
    bpy.app.timers.register(wrapper, first_interval=first_interval, persistent=persistent)
    return wrapper


def clear_timers():
    for cb in list(_timer_callbacks):
        clear_timer(cb)


def clear_timer(cb: types.TimerCallback | None):
    if cb is None:
        return
    _timer_callbacks.discard(cb)
    if bpy.app.timers.is_registered(cb):
        bpy.app.timers.unregister(cb)


def set_timeout(handler, seconds: float | None = 0):
    def wrapper():
        handler()
        return None

    return register_timer(wrapper, seconds or 0)


def set_interval(handler, seconds: float, max_attempts: int | None = None):
    attempts = 0

    def wrapper():
        nonlocal attempts
        handler()
        attempts += 1
        if max_attempts and attempts >= max_attempts:
            return None
        return seconds

    return register_timer(wrapper, seconds)



def setup_logging():
    global _file_handler, LOG_PATH
    teardown_logging()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    try:
        LOG_PATH = get_config_path(os.path.join("logs", "exciton.log"))
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        _file_handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
        )
        _file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(module)s: %(message)s"))


        _file_handler.setLevel(logging.DEBUG)
        logger.addHandler(_file_handler)
    except Exception as e:
        print("EXCITON: Couldn't open log file:", e)

    if IS_DEBUG:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("EXCITON %(levelname)s: %(message)s"))
        logger.addHandler(console_handler)

    logger.info(
        "Exciton %s on Blender %s (%s), %s %s, Python %s, server %s",
        EXTENSION_VERSION,
        bpy.app.version_string,
        bpy.app.build_hash.decode(errors="replace"),
        platform.platform(),
        platform.machine(),
        platform.python_version(),
        WEB_APP_URL,
    )


def teardown_logging():
    global _file_handler
    _file_handler = None
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def _read_extension_version() -> str:
    try:
        with open(pathlib.Path(__file__).parent.parent / "blender_manifest.toml", "rb") as f:
            return str(tomllib.load(f).get("version", "unknown"))
    except Exception:
        return "unknown"


EXTENSION_VERSION = _read_extension_version()



def version_label() -> str:
    return EXTENSION_VERSION + (" (Dev)" if IS_DEV else "")



def version_summary() -> str:
    build = bpy.app.build_hash.decode(errors="replace")
    return f"Exciton {version_label()}, Blender {bpy.app.version_string} ({build}), {platform.platform()}"



def client_label() -> str:
    system = {"darwin": "Mac", "win32": "Windows"}.get(sys.platform, "Linux")
    return f"Blender {bpy.app.version_string} on {system}"




def was_recent(ref: float | None, secs: float, now: float | None = None) -> bool:
    if ref is None:
        return False
    return (monotonic() if now is None else now) - ref < secs


def get_config_path(path):
    base = ""
    if sys.platform == "win32":
        base = os.path.expanduser("~/AppData/Roaming")
    else:
        base = os.path.expanduser("~/.config")


    os.makedirs(os.path.join(base, "exciton-dev"), exist_ok=True)
    return os.path.join(base, "exciton-dev", path)


def random_id():
    return uuid.uuid4().hex


T = tp.TypeVar("T")


def list_get(items: list[T], index: int) -> T | None:
    if 0 <= index < len(items):
        return items[index]
    return None



def start_thread(target):
    def run():
        try:
            target()
        except Exception:
            logger.exception("Thread failed")

    set_timeout(lambda: threading.Thread(target=run, daemon=True).start(), 0)



def run_async(fn, *args, on_done: types.AnyFunction | None = None, on_error: types.ErrorCallbackFunction | None = None, **kwargs):
    def worker():
        try:
            result = fn(*args, **kwargs)
            if on_done:
                set_timeout(lambda: on_done(result), 0)
        except Exception as _e:
            if on_error:
                set_timeout(lambda e=_e: on_error(e), 0)
            else:
                logger.exception("Async call to %s failed", getattr(fn, "__qualname__", fn))

    start_thread(worker)


def redraw_panel():
    if not bpy.context.window:
        return

    for area in bpy.context.window.screen.areas:
        if area.type == "VIEW_3D":
            for region in area.regions:
                if region.type == "UI":
                    region.tag_redraw()
                    break



def redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def register(classes: list | tuple):
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister(classes: list | tuple):
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


CLIENT_RUNTIME_ID = random_id()
