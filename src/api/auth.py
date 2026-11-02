import secrets
import webbrowser
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from .. import utils
from .. import configs
from .. import registry as rg


SIGN_IN_TIMEOUT_SECONDS = 10 * 60




class CallbackServer(HTTPServer):
    def __init__(self):
        super().__init__(("localhost", 0), CallbackHandler)
        self.state = secrets.token_urlsafe(32)
        self.done = False


_server: CallbackServer | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    server: CallbackServer



    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        token = params.get("token", [None])[0]
        state = params.get("state", [""])[0]

        if self.server.done or not token or not secrets.compare_digest(state.encode(), self.server.state.encode()):

            utils.logger.warning("Sign-in callback without a token or with the wrong state")
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Invalid sign-in</h1></body></html>")
            return

        self.server.done = True
        utils.logger.info("Sign-in callback received a token")

        utils.set_timeout(lambda: _store_token(token), 0)

        self.send_response(303)
        self.send_header("Location", f"{utils.WEB_APP_URL}/blender-success")
        self.end_headers()


        _stop_server_async(self.server)


def _store_token(token: str):
    config = configs.get_config()
    config["token"] = token
    configs.persist()
    rg.Overseer.on_signed_in()


def _stop_server_async(server: CallbackServer):
    def stop():
        global _server
        server.shutdown()
        server.server_close()
        if _server is server:
            _server = None

    threading.Thread(target=stop, daemon=True).start()




def _install_id() -> str:
    config = configs.get_config()
    install_id = config.get("install_id")
    if not install_id:
        install_id = config["install_id"] = secrets.token_urlsafe(16)
        configs.persist()
    return install_id


def sign_in():
    global _server


    if _server:
        _stop_server_async(_server)
    server = _server = CallbackServer()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    timer = threading.Timer(SIGN_IN_TIMEOUT_SECONDS, lambda: _stop_server_async(server))
    timer.daemon = True
    timer.start()

    query = urllib.parse.urlencode({"port": port, "state": server.state, "install": _install_id()})
    utils.logger.info("Sign-in started, waiting for callback on port %d", port)
    webbrowser.open(f"{utils.WEB_APP_URL}/sign-in?{query}")
