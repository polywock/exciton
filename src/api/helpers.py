import requests
import typing as tp
import websocket
from .. import utils


T = tp.TypeVar("T")


def parse_response_json(r: requests.Response, cast_as: tp.Type[T]) -> T:
    try:
        return tp.cast(T, r.json())
    except Exception:
        return tp.cast(T, {})



def auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or ''}", "X-Client-Version": utils.EXTENSION_VERSION}



def ws_url(path: str) -> str:
    return f"{utils.WEB_APP_URL.replace('http', 'ws', 1)}{path}"



def is_normal_close(error: tp.Any) -> bool:
    return isinstance(error, websocket.ABNF) and error.opcode == websocket.ABNF.OPCODE_CLOSE
