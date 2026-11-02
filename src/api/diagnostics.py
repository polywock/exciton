import os
import platform
import typing as tp
from time import monotonic
import bpy
import requests
from .. import configs
from .. import types
from .. import utils
from .. import registry as rg
from . import helpers
from .. import shortcut
from ..ribbon import audio
from ..ribbon import recorder


SENT_FEEDBACK_SECONDS = 3

SEND_COOLDOWN_SECONDS = 60

REQUEST_NOTICE_SECONDS = 3


MAX_LOG_BYTES = 490_000



def send():
    data = configs.get_config()
    if not can_send(data):
        return
    data["_diagnostics"] = {"state": "SENDING"}
    utils.redraw_panel()

    utils.logger.info("Sending diagnostics")
    payload = {"env": _collect_env(), "log": _read_log_tail()}
    utils.run_async(
        requests.post,
        f"{utils.WEB_APP_URL}/api/diagnostics",
        json=payload,
        timeout=30,
        on_done=_handle_done,
        on_error=_handle_error,
        headers={**helpers.auth_headers(data.get("token")), "X-Fetch": "true"},
    )




def answer_request(request_id: str):
    data = configs.get_config()
    utils.logger.info("Diagnostics requested from the website")
    payload = {"env": _collect_env(), "log": _read_log_tail(), "requestId": request_id}
    utils.run_async(
        requests.post,
        f"{utils.WEB_APP_URL}/api/diagnostics",
        json=payload,
        timeout=30,
        on_done=_handle_request_done,
        on_error=lambda e: utils.logger.warning("Diagnostics for the website failed: %s: %s", type(e).__name__, e),
        headers={**helpers.auth_headers(data.get("token")), "X-Fetch": "true"},
    )


def _handle_request_done(r: requests.Response):
    if r.status_code != 200:
        utils.logger.warning("Diagnostics for the website returned %s: %s", r.status_code, r.text[:200])
        return

    rg.Overlay.center.show("Diagnostics shared with the Exciton website", REQUEST_NOTICE_SECONDS, area=None)


def _handle_done(r: requests.Response):
    data = configs.get_config()
    body = helpers.parse_response_json(r, dict)
    if r.status_code == 200 and body.get("code"):
        utils.logger.info("Diagnostics sent: %s", body["code"])
        data["_diagnostics"] = {"state": "SENT", "sent_at": monotonic()}

        utils.set_timeout(utils.redraw_panel, SENT_FEEDBACK_SECONDS + 0.1)
        utils.set_timeout(utils.redraw_panel, SEND_COOLDOWN_SECONDS + 0.1)
    else:
        utils.logger.warning("Diagnostics upload returned %s: %s", r.status_code, r.text[:200])
        data["_diagnostics"] = {"state": "FAILED", "error": body.get("error") or f"Server error ({r.status_code})"}
    utils.redraw_panel()


def can_send(data: types.Config) -> bool:
    status = data.get("_diagnostics") or {}
    if status.get("state") == "SENDING":
        return False
    return not (status.get("state") == "SENT" and utils.was_recent(status.get("sent_at"), SEND_COOLDOWN_SECONDS))


def _handle_error(e: Exception):
    utils.logger.warning("Diagnostics upload failed: %s: %s", type(e).__name__, e)
    configs.get_config()["_diagnostics"] = {"state": "FAILED", "error": "Couldn't reach the server"}
    utils.redraw_panel()


def _collect_env() -> dict[str, tp.Any]:
    data = configs.get_config()
    snapshot = data.get("_active_snapshot") or {}
    prefs = bpy.context.preferences
    keyconfigs = bpy.context.window_manager.keyconfigs
    return {
        "extension_version": utils.EXTENSION_VERSION,
        "blender_version": bpy.app.version_string,
        "blender_build": bpy.app.build_hash.decode(errors="replace"),
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "client_runtime_id": utils.CLIENT_RUNTIME_ID,
        "online_access": utils.allows_internet(),
        "channel_open": rg.Channel.is_open(),
        "snapshot_id": snapshot.get("id"),
        "snapshot_loaded": bool(data.get("_active_snapshot")),
        "shortcuts": snapshot.get("shortcuts") or [],
        "shortcut_slots": len(shortcut._State.expected),
        "shortcut_repairs": shortcut._State.repairs,

        "keyconfig": keyconfigs.active.name if keyconfigs.active else None,
        "addons": sorted(prefs.addons.keys()),
        "portaudio_error": audio.portaudio_error,
        "selected_mic": (data.get("selected_mic") or {}).get("name"),
        "prime_mic": bool(data.get("prime_mic")),
        "mic_stream_open": recorder.Recorder.is_stream_open(),
    }



def _read_log_tail() -> str:
    if not utils.LOG_PATH:
        return ""
    chunks: list[bytes] = []
    remaining = MAX_LOG_BYTES
    for path in (utils.LOG_PATH, f"{utils.LOG_PATH}.1"):
        if remaining <= 0:
            break
        try:
            with open(path, "rb") as f:
                size = f.seek(0, os.SEEK_END)
                f.seek(max(0, size - remaining))
                chunk = f.read()
        except OSError:
            break
        chunks.insert(0, chunk)
        remaining -= len(chunk)

    text = b"".join(chunks).decode("utf-8", errors="replace")

    if remaining <= 0 and "\n" in text:
        text = text.split("\n", 1)[1]
    return text
