import typing as tp
import requests
from .. import utils
from . import helpers




def report(token: str, body: str, on_done: tp.Callable[[], None]):
    def handle(r: requests.Response):
        if r.status_code == 200:
            on_done()
        else:
            utils.logger.warning("Add-on operators report returned %s: %s", r.status_code, r.text[:200])

    utils.run_async(
        requests.post,
        f"{utils.WEB_APP_URL}/api/addon-operators",
        data=body,
        timeout=20,
        on_done=handle,
        on_error=lambda e: utils.logger.info("Add-on operators report failed: %s: %s", type(e).__name__, e),
        headers={**helpers.auth_headers(token), "Content-Type": "application/json", "X-Fetch": "true"},
    )
