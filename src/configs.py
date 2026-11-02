import tempfile
import json
import os
import atexit
from . import types
from . import utils


_data: types.Config | None = None
_data_path = utils.get_config_path("data.json")

_save_timer: types.TimerCallback | None = None
_DEBOUNCE_SECONDS = 3



def _ensure_loaded():
    global _data
    if _data is not None:
        return
    try:
        with open(_data_path, "r", encoding="utf-8") as f:
            _data = json.load(f)
    except FileNotFoundError:
        pass
    except Exception:

        utils.logger.exception("Couldn't read %s, starting fresh", _data_path)
    _data = _data or {}


def get_config() -> types.Config:
    _ensure_loaded()
    return _data



def persist():
    global _save_timer
    _cancel_save()
    _save_timer = utils.set_timeout(force_persist, _DEBOUNCE_SECONDS)


def force_persist():
    _cancel_save()
    _write()




def close():
    force_persist()
    atexit.unregister(_write)


def _cancel_save():
    global _save_timer
    utils.clear_timer(_save_timer)
    _save_timer = None




def _write():
    if _data is None:
        return
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_data_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump({k: v for k, v in _data.items() if not k.startswith("_")}, f, indent=2)
        os.replace(tmp, _data_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise



atexit.register(_write)
