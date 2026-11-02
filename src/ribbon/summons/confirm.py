













import hashlib
import math
import textwrap
import typing as tp
import time
from dataclasses import dataclass, field
from time import monotonic
import bpy
from ... import configs
from ... import utils
from ... import windows



PERMISSIONS: dict[str, str] = {
    "RUN_PROGRAMS": "Run other programs on your computer",
    "RUN_LATER": "Leave code in Blender that runs later (handlers, timers, drivers)",
    "CHANGE_PREFERENCES": "Change Blender's preferences or add-ons",
    "INTERNET": "Use the internet",
    "CHANGE_FILES": "Create, change or delete files on your computer",
    "READ_FILES": "Read files on your computer",
    "SEE_SCREEN": "See your Blender window (a screenshot sent to the AI)",
}

SHORT_NAMES: dict[str, str] = {
    "RUN_PROGRAMS": "running programs",
    "RUN_LATER": "code that runs later",
    "CHANGE_PREFERENCES": "preferences and add-ons",
    "INTERNET": "the internet",
    "CHANGE_FILES": "changing files",
    "READ_FILES": "reading files",
    "SEE_SCREEN": "screenshots",
}



DURATIONS: dict[str, tuple[str, float | None]] = {
    "SESSION": ("Until Blender closes", None),
    "DAY": ("1 day", 24 * 60 * 60),
    "WEEK": ("1 week", 7 * 24 * 60 * 60),
    "MONTH": ("30 days", 30 * 24 * 60 * 60),
}

LEAD_IN_SECONDS = 0.4


CONFIRM_SECONDS = 120
DIALOG_WIDTH = 460

MAX_EXPLANATION_CHARS = 400
MAX_PERMISSION_CHARS = 40

CODE_DIALOG_WIDTH = 600
MAX_CODE_LINES = 40
CODE_LINE_CHARS = 90


MAX_APPROVED_SCRIPTS = 500
MAX_REVIEWS = 200
REVIEW_SECONDS = 30 * 24 * 60 * 60

REVIEW_VERSION = 2

CODE_DURATIONS = {key: DURATIONS[key] for key in ("SESSION", "WEEK", "MONTH")}


VERDICTS: dict[str, tuple[str, bool, str]] = {
    "SAFE": ("Appears safe", False, "CHECKMARK"),
    "CAUTION": ("Goes beyond your scene: check it's what you asked for", False, "ERROR"),
    "HARMFUL": ("Blocked: it looks harmful, so it won't run", True, "CANCEL"),
}



@dataclass(frozen=True)
class Kind:
    title: str
    intro: str
    rejected: str
    no_answer: str
    ended: str
    busy: str
    failed: str

    blocked: str = ""


SCRIPT = Kind(
    title="Allow this script?",
    intro="The AI wants to run a script that will:",
    rejected="The user didn't allow this script, so it didn't run. Don't retry it on your own; tell the user what you couldn't do.",
    no_answer="The user didn't answer whether to allow this script, so it didn't run.",
    ended="The request ended before the user allowed this script, so it didn't run.",
    busy="Something else is waiting for the user to allow it, so this script didn't run.",
    failed="Blender couldn't ask the user, so the script didn't run.",
)
SCREENSHOT = Kind(
    title="Allow a screenshot?",
    intro="The AI wants to:",
    rejected="The user didn't allow a screenshot, so none was taken. Don't retry it on your own.",
    no_answer="The user didn't answer whether to allow a screenshot, so none was taken.",
    ended="The request ended before the user allowed a screenshot, so none was taken.",
    busy="Something else is waiting for the user to allow it, so no screenshot was taken.",
    failed="Blender couldn't ask the user, so no screenshot was taken.",
)

COMMAND_SCRIPT_RUN = Kind(
    title="Run this voice command?",
    intro="Runs a script",
    rejected="not allowed",
    no_answer="no answer",
    ended="the request ended",
    busy="something else is waiting for an answer",
    failed="Blender couldn't ask",
    blocked="it looks harmful",
)


ADDON_OPERATOR = Kind(
    title="Run this voice command?",
    intro="Runs an add-on's operator",
    rejected="not allowed",
    no_answer="no answer",
    ended="the request ended",
    busy="something else is waiting for an answer",
    failed="Blender couldn't ask",
)

_CODE_KINDS = (COMMAND_SCRIPT_RUN, ADDON_OPERATOR)


@dataclass
class _Pending:
    id: str
    explanation: str

    permissions: list[str]

    is_active: tp.Callable[[], bool]
    on_allow: tp.Callable[[], None]
    on_reject: tp.Callable[[str], None]
    kind: Kind = SCRIPT

    intro: str = ""


    code: str = ""
    review: dict | None = None

    operator: dict | None = None

    approve_key: str = ""

    remember: bool = True
    asked_at: float = field(default_factory=monotonic)
    timers: list = field(default_factory=list)

    window: tp.Any = None


    @property
    def blocked(self) -> bool:
        return bool(self.code and self.review and self.review["verdict"] == "HARMFUL")


_pending: dict[str, _Pending] = {}
_device: tp.Any = None



def parse_permissions(value: tp.Any) -> list[str]:
    declared = (
        {p.strip()[:MAX_PERMISSION_CHARS] for p in value if isinstance(p, str) and p.strip()}
        if isinstance(value, list)
        else set()
    )
    return [p for p in PERMISSIONS if p in declared] + sorted(declared - PERMISSIONS.keys())




def needs_asking(permissions: list[str]) -> bool:
    return bool(set(permissions) - allowed_now().keys())




def allowed_now() -> dict[str, float | None]:
    data = configs.get_config()
    saved = data.get("script_always_allow")
    now = time.time()
    allowed: dict[str, float | None] = {}
    if isinstance(saved, dict):
        allowed = {p: until for p, until in saved.items() if p in PERMISSIONS and isinstance(until, (int, float)) and until > now}
    for p in data.get("_script_always_allow_session") or []:
        allowed.setdefault(p, None)
    return allowed


def clear_allowed():
    data = configs.get_config()
    data["script_always_allow"] = {}
    data["_script_always_allow_session"] = []
    data["approved_command_scripts"] = {}
    data["_approved_command_scripts_session"] = []
    configs.persist()
    utils.logger.info("Scripts ask again for every permission, and script commands before they run")


def _script_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8", "surrogatepass")).hexdigest()




def _approved() -> dict[str, float | None]:
    data = configs.get_config()
    saved = data.get("approved_command_scripts")
    now = time.time()
    approved: dict[str, float | None] = {}
    if isinstance(saved, dict):
        approved = {h: until for h, until in saved.items() if isinstance(until, (int, float)) and until > now}
    for h in data.get("_approved_command_scripts_session") or []:
        approved.setdefault(h, None)
    return approved



def is_approved(code: str) -> bool:
    return _script_hash(code) in _approved()



def approve(code: str, duration: str = "SESSION"):
    digest = _script_hash(code)
    data = configs.get_config()
    label, seconds = CODE_DURATIONS.get(duration, CODE_DURATIONS["SESSION"])
    if seconds is None:
        data["_approved_command_scripts_session"] = sorted(set(data.get("_approved_command_scripts_session") or []) | {digest})
    else:

        saved = {h: until for h, until in _approved().items() if until is not None}
        saved[digest] = max(saved.get(digest, 0), time.time() + seconds)
        data["approved_command_scripts"] = dict(sorted(saved.items(), key=lambda item: item[1])[-MAX_APPROVED_SCRIPTS:])
        configs.persist()
    utils.logger.info("Script command code %s allowed: %s", digest[:12], label.lower())


def approved_count() -> int:
    return len(_approved())



def parse_review(value: tp.Any) -> dict | None:
    if not isinstance(value, dict) or value.get("verdict") not in VERDICTS:
        return None
    summary = value.get("summary")
    return {
        "verdict": value["verdict"],
        "summary": summary.strip()[:MAX_EXPLANATION_CHARS] if isinstance(summary, str) else "",
        "permissions": parse_permissions(value.get("permissions")),
    }



def cached_review(code: str) -> dict | None:
    saved = configs.get_config().get("command_script_reviews")
    entry = saved.get(_script_hash(code)) if isinstance(saved, dict) else None
    if (
        not isinstance(entry, dict)
        or entry.get("version") != REVIEW_VERSION
        or not isinstance(entry.get("at"), (int, float))
        or time.time() - entry["at"] > REVIEW_SECONDS
    ):
        return None
    return parse_review(entry.get("review"))


def keep_review(code: str, review: dict):
    data = configs.get_config()
    saved = data.get("command_script_reviews")
    now = time.time()
    fresh = {
        h: entry
        for h, entry in (saved.items() if isinstance(saved, dict) else [])
        if isinstance(entry, dict)
        and entry.get("version") == REVIEW_VERSION
        and isinstance(entry.get("at"), (int, float))
        and now - entry["at"] <= REVIEW_SECONDS
    }
    fresh[_script_hash(code)] = {"review": review, "at": now, "version": REVIEW_VERSION}
    data["command_script_reviews"] = dict(sorted(fresh.items(), key=lambda item: item[1]["at"])[-MAX_REVIEWS:])
    configs.persist()


def is_asking() -> bool:
    _prune()
    return bool(_pending)





def ask(
    id: str,
    explanation: str,
    permissions: list[str],
    is_active: tp.Callable[[], bool],
    on_allow: tp.Callable[[], None],
    on_reject: tp.Callable[[str], None],
    kind: Kind = SCRIPT,
    intro: str = "",
    code: str = "",
    review: dict | None = None,
    remember: bool = True,
    operator: dict | None = None,
    approve_key: str = "",
):
    if is_asking():
        on_reject(kind.busy)
        return
    pending = _Pending(
        id=id,
        explanation=explanation.strip()[:MAX_EXPLANATION_CHARS],
        permissions=permissions,
        is_active=is_active,
        on_allow=on_allow,
        on_reject=on_reject,
        kind=kind,
        intro=intro,
        code=code,
        review=review,
        operator=operator,
        approve_key=approve_key or code,
        remember=remember,
    )
    _pending[id] = pending
    utils.logger.info("Asking to allow %s %s: %s", kind.title, id, ", ".join(permissions))
    if code:

        utils.logger.info("The script asked about (%s):\n%s", _script_hash(code)[:12], code)
    _play_cue()
    utils.redraw_all()
    pending.timers = [
        utils.set_timeout(lambda: _open_dialog(id), LEAD_IN_SECONDS),
        utils.set_timeout(lambda: _decide(id, False, kind.no_answer), CONFIRM_SECONDS),
    ]




def attention_alpha(now: float) -> float:
    _prune()
    if not _pending:
        return 0.0
    since = now - min(p.asked_at for p in _pending.values())
    if since < LEAD_IN_SECONDS:
        return 0.35 + 0.45 * abs(math.sin(since / LEAD_IN_SECONDS * 2 * math.pi))
    return 0.6


def cancel_all():
    for p in list(_pending.values()):
        _decide(p.id, False, p.kind.ended)





def _prune():
    for p in list(_pending.values()):
        if not p.is_active():
            _decide(p.id, False, p.kind.ended)







def _decide(
    id: str,
    allowed: bool,
    reason: str | None = None,
    always: list[str] | None = None,
    duration: str = "SESSION",
    answered: bool = False,
):
    pending = _pending.pop(id, None)
    if not pending:
        return
    for timer in pending.timers:
        utils.clear_timer(timer)
    if not answered:
        _close_dialog(pending.window)
    utils.redraw_all()
    if allowed and not pending.is_active():
        utils.logger.info("%s %s allowed after its request ended: not done", pending.kind.title, id)
        return
    reason = reason or pending.kind.rejected
    utils.logger.info("%s %s %s", pending.kind.title, id, "allowed" if allowed else f"not done: {reason}")
    if not allowed:
        pending.on_reject(reason)
        return
    if always:
        _always_allow(always, duration)
    if pending.approve_key and pending.remember:
        approve(pending.approve_key, duration)
    pending.on_allow()


def _always_allow(permissions: list[str], duration: str):
    data = configs.get_config()
    permissions = [p for p in permissions if p in PERMISSIONS]
    seconds = DURATIONS.get(duration, DURATIONS["SESSION"])[1]
    if seconds is None:
        data["_script_always_allow_session"] = sorted(set(data.get("_script_always_allow_session") or []) | set(permissions))
    else:

        saved = {p: until for p, until in allowed_now().items() if until is not None}
        until = time.time() + seconds
        for p in permissions:
            saved[p] = max(saved.get(p, 0), until)
        data["script_always_allow"] = saved
        configs.persist()
    utils.logger.info(
        "Scripts not asked about %s: %s", DURATIONS.get(duration, DURATIONS["SESSION"])[0].lower(), ", ".join(permissions)
    )


def _open_dialog(id: str):
    pending = _pending.get(id)
    if not pending:
        return

    window = windows.chat_window()
    if not window:
        return _decide(id, False, pending.kind.failed)

    area = max(window.screen.areas, key=lambda a: a.width * a.height, default=None)
    region = next((r for r in area.regions if r.type == "WINDOW"), None) if area else None
    if not area or not region:
        return _decide(id, False, pending.kind.failed)
    try:
        with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
            bpy.ops.exciton.confirm_script("INVOKE_DEFAULT", summon_id=id)
        pending.window = window
    except Exception:
        utils.logger.warning("Couldn't open the confirmation dialog", exc_info=True)
        _decide(id, False, pending.kind.failed)




def _close_dialog(window: tp.Any):

    if not windows.is_open(window):
        return
    try:
        with bpy.context.temp_override(window=window, screen=window.screen):
            window.workspace = window.workspace
    except Exception:
        utils.logger.info("Couldn't close the confirmation dialog", exc_info=True)



def _play_cue():
    global _device
    try:
        import aud

        _device = _device or aud.Device()
        low = aud.Sound.sine(660).limit(0, 0.08).fadeout(0.06, 0.02)
        high = aud.Sound.sine(990).limit(0, 0.12).fadeout(0.09, 0.03)
        _device.play(low.join(high).volume(0.25))
    except Exception:
        utils.logger.info("Couldn't play the confirmation cue", exc_info=True)




def _allowable(pending: _Pending) -> list[str]:
    if pending.kind in _CODE_KINDS:
        return []
    allowed = allowed_now()
    return [p for p in pending.permissions if p in PERMISSIONS and p not in allowed]


_PERMISSION_INDEX = {p: i for i, p in enumerate(PERMISSIONS)}


def _wrap(layout: bpy.types.UILayout, text: str, width: int = 70):
    col = layout.column(align=True)
    for paragraph in text.splitlines():
        for line in textwrap.wrap(paragraph, width=width) or [""]:
            col.label(text=line)




def code_lines(code: str) -> tuple[list[str], int]:
    lines = code.expandtabs(4).splitlines()
    shown: list[str] = []
    for i, line in enumerate(lines):
        pieces = [line[j : j + CODE_LINE_CHARS] for j in range(0, len(line), CODE_LINE_CHARS)] or [""]
        if len(shown) + len(pieces) > MAX_CODE_LINES:
            return shown, len(lines) - i
        shown += pieces
    return shown, 0


class EXCITON_OT_confirm_script(bpy.types.Operator):
    bl_idname = "exciton.confirm_script"
    bl_label = "Allow this script?"
    bl_options = {"INTERNAL"}

    summon_id: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    always_allow: bpy.props.BoolVectorProperty(size=len(PERMISSIONS), options={"SKIP_SAVE"})

    always_allow_duration: bpy.props.EnumProperty(
        items=[(key, label, "") for key, (label, _) in DURATIONS.items()], default="SESSION", options={"SKIP_SAVE"}
    )

    allow_for: bpy.props.EnumProperty(
        items=[(key, label, "") for key, (label, _) in CODE_DURATIONS.items()], default="SESSION", options={"SKIP_SAVE"}
    )

    def invoke(self, context, event):
        pending = _pending.get(self.summon_id)
        if not pending:
            return {"CANCELLED"}


        if pending.operator:
            self.allow_for = "MONTH"

        return context.window_manager.invoke_props_dialog(
            self,
            width=CODE_DIALOG_WIDTH if pending.code or pending.operator else DIALOG_WIDTH,
            title="Voice command blocked" if pending.blocked else pending.kind.title,
            confirm_text="OK" if pending.blocked else "Allow",
            cancel_default=True,
        )

    def draw(self, context):
        layout = self.layout
        pending = _pending.get(self.summon_id)
        if not pending:
            layout.label(text="This request has ended.")
            return

        layout.label(text=pending.intro or pending.kind.intro, icon="SCREEN_BACK" if pending.kind is SCREENSHOT else "SCRIPT")
        if pending.code:
            self._draw_code(layout, pending)
            return
        if pending.operator:
            self._draw_operator(layout, pending.operator)
            return
        if pending.permissions:
            box = layout.box()
            box.alert = True
            for permission in pending.permissions:
                box.label(text=PERMISSIONS.get(permission, permission), icon="ERROR")

        if pending.explanation:
            _wrap(layout.box(), pending.explanation)
        if pending.kind is SCREENSHOT:


            layout.prop(self, "always_allow_duration", text="Allow for")
            return

        allowable = _allowable(pending)
        if allowable:

            header, body = layout.panel("EXCITON_script_always_allow", default_closed=True)
            header.label(text="Don't ask again")
            if body:
                for permission in allowable:
                    body.prop(
                        self, "always_allow", index=_PERMISSION_INDEX[permission], text=SHORT_NAMES[permission].capitalize()
                    )
                body.prop(self, "always_allow_duration", text="For")



    def _draw_operator(self, layout: bpy.types.UILayout, operator: dict):
        box = layout.box()
        box.label(text=operator["label"], icon="PLUGIN")
        source = box.row()
        source.active = False
        source.label(text=f"{operator['key']} · from the {operator['addon']} add-on")
        if operator.get("description"):
            _wrap(box, operator["description"], width=90)
        if operator.get("options"):
            col = layout.box().column(align=True)
            for name, value, is_path in operator["options"]:
                row = col.row()
                row.alert = is_path
                row.label(text=f"{name}: {value}", icon="FILE_FOLDER" if is_path else "DOT")
        note = layout.row()
        note.active = False
        note.label(text="Exciton doesn't check add-ons: allow it if you trust this one.")
        layout.prop(self, "allow_for", text="Allow for")


    def _draw_code(self, layout: bpy.types.UILayout, pending: _Pending):
        review = pending.review or {"verdict": "HARMFUL", "summary": "", "permissions": []}
        verdict, alert, icon = VERDICTS[review["verdict"]]
        box = layout.box()
        row = box.row()
        row.alert = alert
        row.label(text=verdict, icon=icon)
        if review["summary"]:
            _wrap(box, review["summary"], width=90)
        for permission in review["permissions"]:
            line = box.row()
            line.alert = True
            line.label(text=PERMISSIONS.get(permission, permission), icon="ERROR")
        note = box.row()
        note.active = False
        note.label(text="Checked by AI, which can be wrong.")


        header, body = layout.panel("EXCITON_command_script_code", default_closed=True)
        header.label(text="See code")
        if body:
            lines, left_out = code_lines(pending.code)
            col = body.box().column(align=True)
            for line in lines:
                col.label(text=line)
            if left_out:
                note = body.row()
                note.alert = True
                note.label(text=f"{left_out} more lines not shown: the whole script is in Exciton's log (Open Logs).")

        if pending.blocked:
            note = layout.row()
            note.active = False
            note.label(text="If it's your command, ask the chat to change it.")
        else:
            layout.prop(self, "allow_for", text="Allow for")

    def execute(self, context):
        pending = _pending.get(self.summon_id)
        if pending and pending.blocked:
            _decide(self.summon_id, False, pending.kind.blocked, answered=True)
            return {"FINISHED"}
        if pending and pending.kind is SCREENSHOT:
            _decide(self.summon_id, True, always=["SEE_SCREEN"], duration=self.always_allow_duration, answered=True)
            return {"FINISHED"}
        ticked = [p for p in _allowable(pending) if self.always_allow[_PERMISSION_INDEX[p]]] if pending else []
        duration = self.allow_for if pending and pending.approve_key else self.always_allow_duration
        _decide(self.summon_id, True, always=ticked, duration=duration, answered=True)
        return {"FINISHED"}

    def cancel(self, context):
        pending = _pending.get(self.summon_id)
        _decide(self.summon_id, False, pending.kind.blocked if pending and pending.blocked else None, answered=True)


classes = (EXCITON_OT_confirm_script,)


def register():
    utils.register(classes)


def unregister():
    cancel_all()
    utils.unregister(classes)
