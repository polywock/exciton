

import typing as tp

from .. import configs
from .. import registry as rg
from .. import utils
from . import td




NOTICE_CODES = {
    "NO_SPEECH",
    "NO_MATCH",
    "NOT_AVAILABLE",
    "RATE_LIMITED",
    "QUOTA_EXCEEDED",
    "PLAN_REQUIRED",
    "AUDIO_TOO_LONG",
    "ACCOUNT_BANNED",
}


class ServerError(tp.NamedTuple):

    reason: str | None
    kind: tp.Literal["error", "notice"]




def handle(msg: td.FromServerMessage, label: str, where: str) -> ServerError:
    code = msg.get("error_code")
    text = msg.get("error")
    if code in NOTICE_CODES:
        utils.logger.info("%s ended: %s (%s)", label, text, code)
    elif code != "CANCELLED" and (text or code):
        utils.logger.warning("%s error in %s: %s (%s)", label, where, text, code)

    match code:
        case "INVALID_AUTH":
            utils.logger.info("Server rejected our token during a job")
            rg.Overseer.sign_out()
        case "UPDATE_REQUIRED":

            configs.get_config()["_update_required"] = {"message": text or "Update the Exciton add-on."}
            utils.redraw_panel()
        case "PLAN_REQUIRED":


            from ..api import snapshot

            snapshot.api_snapshot_rl()

    if code == "CANCELLED":
        return ServerError(None, "notice")
    return ServerError(text or "Server error", "notice" if code in NOTICE_CODES else "error")
