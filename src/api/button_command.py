import typing as tp
import requests
from .. import utils
from . import helpers

TIMEOUT_SECONDS = 15

FAILED = "Exciton couldn't do that. Try again."



def failure_message(status: int, data: dict, text: str) -> str:
    if status == 401:
        return "Sign in to Exciton again."

    if status == 422 and data.get("error"):
        return str(data["error"])
    if status == 403 and text:
        return text[:200]
    return FAILED


def upgrade_path(status: int, data: dict) -> str | None:
    path = data.get("upgradePath")
    return path if status == 422 and isinstance(path, str) else None




def send(token: str, body: dict, on_reply: tp.Callable[[dict | None, str | None, str | None], None]):
    def handle(r: requests.Response):
        data = helpers.parse_response_json(r, dict)
        if r.status_code == 200:
            on_reply(data, None, None)
            return
        utils.logger.warning("Button command returned %s: %s", r.status_code, r.text[:200])
        on_reply(None, failure_message(r.status_code, data, r.text), upgrade_path(r.status_code, data))

    def handle_error(e: Exception):
        utils.logger.info("Button command failed: %s: %s", type(e).__name__, e)
        on_reply(None, "Couldn't reach Exciton. Check your connection and try again.", None)

    utils.run_async(
        requests.post,
        f"{utils.WEB_APP_URL}/api/button-command",
        json=body,
        timeout=TIMEOUT_SECONDS,
        on_done=handle,
        on_error=handle_error,
        headers={**helpers.auth_headers(token), "X-Fetch": "true"},
    )
