import typing as tp

IntPoint: tp.TypeAlias = tuple[int, int]
FloatPoint: tp.TypeAlias = tuple[float, float]
FloatRect: tp.TypeAlias = tuple[float, float, float, float]

ColorTuple: tp.TypeAlias = tuple[float, float, float, float]
AnyFunction: tp.TypeAlias = tp.Callable[..., tp.Any]
ErrorCallbackFunction: tp.TypeAlias = tp.Callable[[Exception], tp.Any]
TimerCallback: tp.TypeAlias = tp.Callable[[], float | None]

ChatOrCommand: tp.TypeAlias = tp.Literal["CHAT", "COMMAND"]
ShortcutAction: tp.TypeAlias = tp.Literal["CHAT", "COMMAND", "CONTROL"]


class FullKey(tp.TypedDict, total=False):
    type: str | None
    shift: bool
    ctrl: bool
    alt: bool
    oskey: bool


class Shortcut(tp.TypedDict):
    trigger: FullKey
    action: ShortcutAction
    disabled: tp.NotRequired[bool | None]


class InputDevice(tp.TypedDict):
    id: int
    name: str


class Snapshot(tp.TypedDict):
    id: str
    shortcuts: list[Shortcut]
    buiFontSize: float | None
    buiMaxWidth: float | None
    buiSpeed: float | None
    debugMode: tp.NotRequired[bool]

    liveChat: tp.NotRequired[bool]

    replyVolume: tp.NotRequired[float]

    commandChecks: tp.NotRequired[dict[str, list[str]]]


class UpdateRequired(tp.TypedDict):
    minVersion: tp.NotRequired[str]
    message: str



class Config(tp.TypedDict, total=False):


    snapshot: Snapshot | None


    _active_snapshot: Snapshot | None
    token: str | None
    install_id: str | None
    selected_mic: InputDevice | None
    prime_mic: bool | None

    mic_levels: dict[str, float] | None

    mic_level_counts: dict[str, int] | None



    script_always_allow: dict[str, float] | None
    _script_always_allow_session: list[str] | None



    approved_command_scripts: dict[str, float] | None

    _approved_command_scripts_session: list[str] | None

    command_script_reviews: dict[str, dict] | None
    _init_complete: bool | None
    _snapshot_loading: bool | None
    _snapshot_loading_latest: float | None
    _snapshot_last_status: bool | None
    _snapshot_last_error_at: float | None
    _update_required: UpdateRequired | None
    _diagnostics: "DiagnosticsStatus | None"

    _test_force_snapshot_500: bool | None
    _test_force_snapshot_401: bool | None

    _test_script_permissions: list[str] | None


class DiagnosticsStatus(tp.TypedDict, total=False):
    state: tp.Required[tp.Literal["SENDING", "SENT", "FAILED"]]
    sent_at: float
    error: str
