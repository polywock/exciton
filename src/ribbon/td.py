import typing as tp

JobState: tp.TypeAlias = tp.Literal["recording", "sealed", "done", "failed"]
ProtocolState: tp.TypeAlias = tp.Literal[
    "1_STARTING",
    "2_OPEN",
    "3_READY_PRELIM",
    "4_SENT_PRELIM",
    "5_READY_AUDIO",
    "6_SENT_AUDIO",
    "CLOSED",
]


class AudioFormat(tp.TypedDict, total=False):
    channels: int
    sampleRate: int
    sampleWidth: int


class Prelim(tp.TypedDict, total=False):
    action: tp.Any
    audioFormat: AudioFormat
    conversationId: str | None
    activeKeymaps: list[str]
    commandContext: dict[str, str]

    unavailableCommands: list[str]

    playsAudio: bool

    jobId: str

    flags: dict


class Update(tp.TypedDict):
    tool: str | None
    text: str | None
    final: bool | None


class FromServerMessage(tp.TypedDict, total=False):
    type: tp.Literal[
        "ERROR",
        "OK",
        "UPDATE",
        "SUMMON",
        "SEND_PRELIM",
        "SEND_AUDIO",
        "ID_ESTABLISHED",
        "RESUME_PROBE",
        "FLAGS",
        "EDGE",
        "STANDBY",
    ]
    error: str

    error_code: tp.Literal[
        "INVALID_AUTH",
        "CANCELLED",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "UPSTREAM_ERROR",
        "CLIENT_ERROR",
        "TIMEOUT",
        "NO_SPEECH",
        "NO_MATCH",
        "NOT_AVAILABLE",
        "AUDIO_TOO_LONG",
        "OPERATOR_FAILED",
        "UPDATE_REQUIRED",
        "QUOTA_EXCEEDED",
        "PLAN_REQUIRED",
        "ACCOUNT_BANNED",
    ]
    summon_type: tp.Literal["RUN_SCRIPT", "RUN_OPERATOR", "RUN_COMMAND_SCRIPT", "SCREENSHOT", "POINT", "WAIT_FOR_USER"]
    summon_id: str
    summon_request: tp.Any
    conversation_id: str
    conversation_resumed: bool

    spoken: bool
    update: Update

    flags: dict

    colo: str
    rtt_ms: int

    received_at: float


class FromClientMessage(tp.TypedDict, total=False):



    type: tp.Literal[
        "START", "KEEPALIVE", "SUMMON_RESULT", "SUMMON_WAITING", "SENT_PRELIM", "INTERRUPT", "CANCEL", "RESUME_PROCEED"
    ]
    summon_id: str
    summon_response: tp.Any
    prelim_payload: Prelim


class SummonScriptRequest(tp.TypedDict, total=False):
    script: str
    is_async: bool

    label: str

    permissions: list[str]
    explanation: str


class OperatorProp(tp.TypedDict, total=False):
    key: str
    value: tp.Any


class SummonOperatorRequest(tp.TypedDict, total=False):
    operator: str
    props: list[OperatorProp]
    label: str
    check: str



class SummonCommandScriptRequest(tp.TypedDict, total=False):
    label: str
    script: str


    review: dict | None


class SummonResponse(tp.TypedDict, total=False):

    status: tp.Literal["OK", "ERROR", "NEEDS_REVIEW"]
    result: str | None

    state: bool
    error: str | None
    logs: list[str]

    truncated: bool

    image: str
    media_type: str
    width: int
    height: int
