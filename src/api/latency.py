import requests
from .. import configs
from .. import utils
from . import helpers







def report(job_id: str, action: str, timings: dict[str, int], connection: str | None = None):
    token = configs.get_config().get("token")
    if not token:
        return
    utils.run_async(
        requests.post,
        f"{utils.WEB_APP_URL}/api/latency",
        json={"jobId": job_id, "action": action, "timings": timings, **({"connection": connection} if connection else {})},
        timeout=10,
        on_done=_handle_done,
        on_error=lambda e: utils.logger.debug("Latency report failed: %s: %s", type(e).__name__, e),
        headers={**helpers.auth_headers(token), "X-Fetch": "true"},
    )


def _handle_done(r: requests.Response):
    if r.status_code != 200:
        utils.logger.debug("Latency report returned %s", r.status_code)
