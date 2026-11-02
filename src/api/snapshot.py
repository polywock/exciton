import random
import typing as tp
from .. import configs
from .. import utils
from . import helpers
from ..commands import addon_operators
from .. import types
import requests
from time import monotonic
from .. import registry as rg


RATE_LIMIT_SECONDS = 6




_RETRY_INITIAL = 2.0
_RETRY_MAX = 60.0




_generation = 0


def api_snapshot():
    global _generation
    _generation += 1

    _cancel_retry()
    data = configs.get_config()
    token = data.get("token")
    data["_snapshot_loading"] = True
    data["_snapshot_loading_latest"] = monotonic()
    params = {}
    current_snapshot = data.get("snapshot")
    if current_snapshot and current_snapshot.get("id"):
        params["our-snapshot"] = current_snapshot.get("id")
    utils.redraw_panel()
    utils.run_async(
        requests.get,
        f"{utils.WEB_APP_URL}/api/snapshot",
        params=params,
        on_done=_if_latest(_generation, token, handle_done),
        on_error=_if_latest(_generation, token, handle_error),
        headers={**helpers.auth_headers(token), "X-Fetch": "true"},
    )


def _if_latest(generation: int, token: str | None, handler: tp.Callable[[tp.Any], None]):
    def handle(result):
        if generation != _generation:
            return
        data = configs.get_config()
        if data.get("token") != token:

            data["_snapshot_loading"] = False
            utils.redraw_panel()
            return
        handler(result)

    return handle


def handle_error(e: Exception):
    utils.logger.warning("Snapshot request failed: %s: %s", type(e).__name__, e)
    data = configs.get_config()
    handle_error_common(data, retry=True)


def handle_done(r: requests.Response):
    data = configs.get_config()
    data["_snapshot_loading"] = False
    force_401 = data.get("_test_force_snapshot_401")
    force_500 = data.get("_test_force_snapshot_500")


    data.pop("_test_force_snapshot_401", 0)
    data.pop("_test_force_snapshot_500", 0)

    if r.status_code == 200 and not (force_401 or force_500):
        payload = helpers.parse_response_json(r, SnapshotResponse)
        data["_snapshot_last_status"] = True
        data["_snapshot_last_error_at"] = None

        data["_update_required"] = payload.get("updateRequired")
        data["snapshot"] = payload.get("snapshot") or data.get("snapshot")
        data["_active_snapshot"] = data["snapshot"]
        snap = data["snapshot"] or {}
        utils.logger.info("Snapshot %s loaded (%d shortcuts)", snap.get("id"), len(snap.get("shortcuts") or []))
        _reset_retry()
        configs.persist()
        rg.Overseer.sync()

        addon_operators.report_soon()
    elif r.status_code == 401 or force_401:
        utils.logger.info("Snapshot request unauthorized")
        rg.Overseer.sign_out()
    else:
        utils.logger.warning("Snapshot request returned %s: %s", r.status_code, r.text[:200])

        handle_error_common(data, retry=bool(force_500) or r.status_code >= 500 or r.status_code == 429)


def handle_error_common(data: types.Config, retry: bool):
    data["_snapshot_loading"] = False
    data["_snapshot_last_status"] = False
    data["_snapshot_last_error_at"] = monotonic()
    data["_active_snapshot"] = None
    rg.Overseer.sync()
    utils.redraw_panel()
    utils.set_timeout(utils.redraw_panel, RATE_LIMIT_SECONDS)
    if retry:
        _schedule_retry()


_retry_timer: types.TimerCallback | None = None
_retry_backoff = _RETRY_INITIAL


def _schedule_retry():
    global _retry_timer, _retry_backoff
    _cancel_retry()
    delay = _retry_backoff * random.uniform(0.5, 1.0)
    _retry_backoff = min(_retry_backoff * 2, _RETRY_MAX)
    utils.logger.info("Snapshot retry in %.0fs", delay)
    _retry_timer = utils.set_timeout(_retry, delay)


def _retry():
    global _retry_timer
    _retry_timer = None
    data = configs.get_config()

    if data.get("token") and utils.allows_internet():
        api_snapshot()


def _cancel_retry():
    global _retry_timer
    utils.clear_timer(_retry_timer)
    _retry_timer = None


def _reset_retry():
    global _retry_backoff
    _cancel_retry()
    _retry_backoff = _RETRY_INITIAL


_trailing_timer: types.TimerCallback | None = None




def api_snapshot_rl():
    global _trailing_timer
    data = configs.get_config()
    latest = data.get("_snapshot_loading_latest")
    if utils.was_recent(latest, RATE_LIMIT_SECONDS):
        if not _trailing_timer:
            delay = tp.cast(float, latest) + RATE_LIMIT_SECONDS - monotonic()
            _trailing_timer = utils.set_timeout(_fetch_trailing, max(delay, 0))
        return
    api_snapshot()


def _fetch_trailing():
    global _trailing_timer
    _trailing_timer = None
    data = configs.get_config()

    if data.get("token") and utils.allows_internet():
        api_snapshot()


class SnapshotResponse(tp.TypedDict, total=False):
    snapshot: types.Snapshot
    updateRequired: types.UpdateRequired
