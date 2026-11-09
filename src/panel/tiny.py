import bpy
import os
import typing as tp
from ..api import auth, snapshot, diagnostics
from .. import utils
from .. import configs
from ..ribbon import device_watch
from ..ribbon import recorder
from ..ribbon.summons import confirm
from .. import types
from .. import registry as rg
import webbrowser
from time import monotonic


_mic_list: list[types.InputDevice] = [{"id": -1, "name": "Default"}]

default_mic_name: str | None = None

PORTAUDIO_INSTALL_COMMAND = "sudo apt install libportaudio2"


DEVICE_CHECK_SECONDS = 2


_device_fingerprint: device_watch.Fingerprint | None = None
MENU_REFRESH_SECONDS = 2
_menu_refreshed_at: float | None = None





def update_devices(for_launch=False) -> bool:
    global _mic_list, default_mic_name, _device_fingerprint
    if not for_launch and (not recorder.Recorder.can_list_new_devices() or not recorder.Recorder.reset()):
        return False

    _device_fingerprint = device_watch.fingerprint()
    devices = recorder.input_devices()
    utils.logger.info("Input devices: %s", [d["name"] for d in devices] if devices is not None else "PortAudio unavailable")
    if devices is not None:
        _mic_list = [{"id": -1, "name": "Default"}]
        _mic_list += devices
        default_mic_name = recorder.default_device_name()
    if not for_launch:
        utils.set_timeout(recorder.Recorder.apply_prime_setting, 0)
        utils.redraw_panel()
    return True




def _check_devices():
    current = device_watch.fingerprint()
    if current is None:
        utils.logger.info("Audio device changes can't be watched here: the mic menu reads the devices as it opens")
        return None
    if current != _device_fingerprint:
        utils.logger.info("Audio devices changed: reading them again")
        update_devices()
    return DEVICE_CHECK_SECONDS


class EXCITON_MT_mic_menu(bpy.types.Menu):
    bl_label = "Select Microphone"
    bl_idname = "EXCITON_MT_mic_menu"

    def draw(self, context):
        global _menu_refreshed_at


        if _device_fingerprint is None and not utils.was_recent(_menu_refreshed_at, MENU_REFRESH_SECONDS):
            _menu_refreshed_at = monotonic()
            update_devices()
        layout = self.layout
        selected = configs.get_config().get("selected_mic")
        checked = recorder.get_matching_device(_mic_list, selected) if selected else None
        for mic in _mic_list:
            op = layout.operator(
                "exciton.select_mic", text=mic_label(mic["name"]), icon="CHECKMARK" if mic == checked else "NONE"
            )
            op.mic_name = mic["name"]
            op.mic_id = mic["id"]

        if default_stands_in():
            layout.separator()
            layout.label(text=f"{FALLBACK_MARK} Not connected or couldn't open, using {mic_label('Default')}")


def mic_label(name: str) -> str:
    return f"Default ({default_mic_name})" if name == "Default" and default_mic_name else name



FALLBACK_MARK = "**"



def default_stands_in() -> bool:
    name = _selected_mic_name()
    if name == "Default":
        return False
    connected = recorder.find_device_by_name(_mic_list, name) is not None
    return not connected or recorder.Recorder.fallback_from == name



def selected_mic_label() -> str:
    name = _selected_mic_name()
    return f"{name}{FALLBACK_MARK}" if default_stands_in() else name


def _selected_mic_name() -> str:
    return (configs.get_config().get("selected_mic") or {}).get("name") or "Default"


class EXCITON_OT_select_mic(bpy.types.Operator):
    bl_idname = "exciton.select_mic"
    bl_label = "Select Mic"

    mic_name: bpy.props.StringProperty()
    mic_id: bpy.props.IntProperty()

    def execute(self, context):
        data = configs.get_config()
        data["selected_mic"] = {"name": self.mic_name, "id": self.mic_id}
        utils.logger.info("Selected microphone %r", self.mic_name)
        configs.persist()


        if not update_devices() and recorder.Recorder.reset():
            recorder.Recorder.apply_prime_setting()
        return {"FINISHED"}


def toggle_prime_mic():
    data = configs.get_config()
    prime_mic = data.get("prime_mic") or False
    data["prime_mic"] = not prime_mic
    utils.logger.info("Keep microphone open: %s", data["prime_mic"])
    recorder.Recorder.apply_prime_setting()
    configs.persist()
    utils.set_timeout(utils.redraw_all, 0)


ActionType = tp.Literal[
    "OPEN_SETTINGS",
    "OPEN_WEBSITE_PATH",
    "SNAPSHOT_RL",
    "SIGN_IN",
    "SIGN_OUT",
    "DELETE_CONFIG_KEY",
    "TOGGLE_KEY",
    "RELOAD_DEVICES",
    "TOGGLE_PRIME_MIC",
    "REDRAW",
    "TOGGLE_CHANNEL",
    "OPEN_LOGS",
    "SEND_DIAGNOSTICS",
    "RELOAD_SETTINGS",
    "COPY_PORTAUDIO_COMMAND",
    "COPY_VERSION",
    "CLEAR_SCRIPT_ALLOWS",
    "TOGGLE_TEST_PERMISSION",
    "MOCK_SCRIPT",
    "MOCK_COMMAND_SCRIPT",
    "MOCK_SCREENSHOT",
    "MOCK_ADDON_OPERATOR",
]



class EXCITON_OT_action(bpy.types.Operator):
    bl_idname = "exciton.action"
    bl_label = "Exciton Action"
    bl_description = "An action from the Exciton panel"

    type: bpy.props.EnumProperty(items=[(t, "", "") for t in tp.get_args(ActionType)])

    target_key: bpy.props.StringProperty()

    def invoke(self, context, event):
        match self.type:
            case "OPEN_SETTINGS":
                webbrowser.open(f"{utils.WEB_APP_URL}/app")
            case "OPEN_WEBSITE_PATH":
                webbrowser.open(f"{utils.WEB_APP_URL}{self.target_key}")
            case "SNAPSHOT_RL":
                snapshot.api_snapshot_rl()
            case "SIGN_IN":
                auth.sign_in()
            case "SIGN_OUT":
                rg.Overseer.sign_out()
            case "DELETE_CONFIG_KEY":
                data = configs.get_config()
                data.pop(self.target_key, 0)
                rg.Overseer.sync()
            case "TOGGLE_KEY":
                data = configs.get_config()
                data[self.target_key] = not data.get(self.target_key)
                utils.redraw_panel()
            case "RELOAD_DEVICES":
                update_devices()
            case "TOGGLE_PRIME_MIC":
                toggle_prime_mic()
            case "REDRAW":
                utils.redraw_panel()
            case "TOGGLE_CHANNEL":
                if rg.Channel.is_open():
                    rg.Channel.disconnect()
                else:
                    rg.Channel.connect(configs.get_config().get("token"))
                utils.set_timeout(utils.redraw_panel, 1)
            case "OPEN_LOGS":
                if not utils.LOG_PATH:
                    self.report({"WARNING"}, "Logging couldn't start, so there are no logs")
                    return {"CANCELLED"}

                bpy.ops.wm.path_open(filepath=os.path.dirname(utils.LOG_PATH))
            case "SEND_DIAGNOSTICS":
                diagnostics.send()
            case "RELOAD_SETTINGS":
                utils.logger.info("Reloading settings")
                rg.Overseer.force_shortcut_resync()
                snapshot.api_snapshot_rl()
            case "COPY_PORTAUDIO_COMMAND":
                context.window_manager.clipboard = PORTAUDIO_INSTALL_COMMAND
                self.report({"INFO"}, "Copied. Run it in a terminal, then restart Blender.")
            case "COPY_VERSION":
                context.window_manager.clipboard = utils.version_summary()
                self.report({"INFO"}, "Copied the versions")
            case "TOGGLE_TEST_PERMISSION":
                data = configs.get_config()
                permissions = set(data.get("_test_script_permissions") or [])
                permissions ^= {self.target_key}
                data["_test_script_permissions"] = sorted(permissions)
                utils.redraw_panel()
            case "MOCK_SCRIPT":
                mock_script()
            case "MOCK_SCREENSHOT":
                mock_screenshot()
            case "MOCK_ADDON_OPERATOR":
                mock_addon_operator()
            case "MOCK_COMMAND_SCRIPT":
                mock_command_script(self.target_key)
            case "CLEAR_SCRIPT_ALLOWS":
                confirm.clear_allowed()
                utils.redraw_panel()

        return {"FINISHED"}


MOCK_SCRIPT_DELAY_SECONDS = 5




def mock_script():
    permissions = confirm.parse_permissions(configs.get_config().get("_test_script_permissions") or [])
    _set_mock_result(f"Asking in {MOCK_SCRIPT_DELAY_SECONDS}s")
    utils.set_timeout(lambda: _ask_mock(permissions), MOCK_SCRIPT_DELAY_SECONDS)


def _ask_mock(permissions: list[str]):

    permissions = [p for p in permissions if p != "SEE_SCREEN"]
    if not confirm.needs_asking(permissions):
        return _set_mock_result("Would run without asking")
    if confirm.is_asking():
        return _set_mock_result("Not asked: another script is waiting")
    _set_mock_result("Asking")
    confirm.ask(
        utils.random_id(),
        "A mock script from the testing panel. Nothing runs, whatever you choose.",
        permissions,
        is_active=lambda: True,
        on_allow=lambda: _set_mock_result("Allowed"),
        on_reject=lambda reason: _set_mock_result(f"Not allowed: {reason}"),
    )



def mock_screenshot():
    _set_mock_result(f"Asking in {MOCK_SCRIPT_DELAY_SECONDS}s")
    utils.set_timeout(_ask_mock_screenshot, MOCK_SCRIPT_DELAY_SECONDS)


def _ask_mock_screenshot():
    if not confirm.needs_asking(["SEE_SCREEN"]):
        return _set_mock_result("Would take it without asking")
    if confirm.is_asking():
        return _set_mock_result("Not asked: another script is waiting")
    _set_mock_result("Asking")
    confirm.ask(
        utils.random_id(),
        "A mock screenshot from the testing panel. Nothing is taken, whatever you choose.",
        ["SEE_SCREEN"],
        is_active=lambda: True,
        on_allow=lambda: _set_mock_result("Allowed"),
        on_reject=lambda reason: _set_mock_result(f"Not allowed: {reason}"),
        kind=confirm.SCREENSHOT,
    )




def mock_addon_operator():
    _set_mock_result(f"Asking in {MOCK_SCRIPT_DELAY_SECONDS}s")
    utils.set_timeout(_ask_mock_addon_operator, MOCK_SCRIPT_DELAY_SECONDS)


def _ask_mock_addon_operator():
    if confirm.is_asking():
        return _set_mock_result("Not asked: another script is waiting")
    _set_mock_result("Asking")
    confirm.ask(
        utils.random_id(),
        "",
        [],
        is_active=lambda: True,
        on_allow=lambda: _set_mock_result("Allowed"),
        on_reject=lambda reason: _set_mock_result(f"Not allowed: {reason}"),
        kind=confirm.ADDON_OPERATOR,
        operator={
            "key": "mesh.looptools_relax",
            "label": "Relax",
            "addon": "LoopTools",
            "description": "Relax the loop, so it is smoother",
            "options": [
                ("Iterations", "3", False),
                ("Interpolation", "“cubic”", False),
                ("Export Path", "“//relaxed/mesh.obj”", True),
            ],
        },
        approve_key="mock",
        remember=False,
    )



_MOCK_COMMAND_CODE = """for i in range(5):
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, i * 2))
resolve("Added 5 monkeys")"""
_MOCK_LONG_LINE = "names = [" + ", ".join(f'"Monkey.{i:03}"' for i in range(20)) + "]"


def _mock_command_code() -> str:
    steps = [f"    bpy.context.active_object.name = names[{i}]" for i in range(confirm.MAX_CODE_LINES)]
    return "\n".join([_MOCK_LONG_LINE, "for i in range(5):", *steps, _MOCK_COMMAND_CODE])



_MOCK_REVIEWS = {
    "SAFE": {"verdict": "SAFE", "summary": "Adds five monkey heads stacked on top of each other.", "permissions": []},
    "CAUTION": {
        "verdict": "CAUTION",
        "summary": "Adds five monkey heads, then saves your file to the desktop as monkeys.blend.",
        "permissions": ["CHANGE_FILES"],
    },
    "HARMFUL": {
        "verdict": "HARMFUL",
        "summary": "Says it adds monkeys, but sends the files in your home folder to a server on the internet.",
        "permissions": ["READ_FILES", "INTERNET"],
    },
}




def mock_command_script(verdict: str):
    _set_mock_result(f"Asking in {MOCK_SCRIPT_DELAY_SECONDS}s")
    utils.set_timeout(lambda: _ask_mock_command(verdict), MOCK_SCRIPT_DELAY_SECONDS)


def _ask_mock_command(verdict: str):
    if confirm.is_asking():
        return _set_mock_result("Not asked: another script is waiting")
    _set_mock_result("Asking")
    confirm.ask(
        utils.random_id(),
        "",
        [],
        is_active=lambda: True,
        on_allow=lambda: _set_mock_result("Allowed"),
        on_reject=lambda reason: _set_mock_result(f"Not allowed: {reason}"),
        kind=confirm.COMMAND_SCRIPT_RUN,
        code=_mock_command_code(),
        review=_MOCK_REVIEWS.get(verdict),
        remember=False,
    )


def _set_mock_result(result: str):
    utils.logger.info("Mock script: %s", result)


classes = (EXCITON_MT_mic_menu, EXCITON_OT_select_mic, EXCITON_OT_action)


def register():
    utils.register(classes)
    utils.set_timeout(lambda: update_devices(True), 0)
    utils.register_timer(_check_devices, DEVICE_CHECK_SECONDS)


def unregister():
    utils.unregister(classes)
