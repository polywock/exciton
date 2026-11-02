import json
import time
import typing as tp
from . import base
from . import confirm
from .. import td
from ... import utils
import bpy



_LOGGED_SCRIPT_CHARS = 4000





MAX_REPLY_CHARS = 20_000




class _ScriptEnded(BaseException):
    pass


class SummonScript(base.SummonBase):
    def __init__(
        self,
        code: str,
        is_async: bool,
        id: str,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        permissions: list[str] | None = None,
        explanation: str = "",
    ):
        super().__init__(id, on_resolve)
        self.code = code
        self.is_async = is_async

        self.permissions = permissions or []
        self.explanation = explanation
        self.logs: list[str] = []


        self._logged = 0
        self._logs_cut = False

        self.undo_anchor: str | None = None

        self._running = False

        self._ending: tuple[str, tp.Any] | None = None

    @classmethod
    def start(cls, msg: td.FromServerMessage, on_resolve: tp.Callable[[td.SummonResponse], None]) -> "SummonScript | None":
        payload: td.SummonScriptRequest | None = msg.get("summon_request")
        id = msg.get("summon_id")

        if not payload or not id:
            return None

        code = payload.get("script")
        if not code or not isinstance(code, str):
            return None

        is_async = payload.get("is_async", False)
        explanation = payload.get("explanation")

        return cls(
            code,
            is_async,
            id,
            on_resolve,
            permissions=confirm.parse_permissions(payload.get("permissions")),
            explanation=explanation if isinstance(explanation, str) else "",
        )



    def write(self, *args, sep=" ", **_options):
        room = MAX_REPLY_CHARS - self._logged
        if room <= 0:
            self._logs_cut = True
            return
        entry = sep.join(str(arg) for arg in args)
        if _length(entry) + 1 > room:
            self._logs_cut = True
            if room <= 1:
                return
            entry = _head(entry, room - 1)
        self.logs.append(entry)
        self._logged += _length(entry) + 1

    def resolve(self, result=None):
        if self._running:
            self._end_early("resolve", result)
        if self.is_done:
            return
        _clear_anchor(self.undo_anchor)
        if self.undo_anchor is not None:
            bpy.ops.ed.undo_push(message="Exciton.ScriptDone")
            self.undo_anchor = None
        super().resolve(str(result) if result is not None else "")

    def reject(self, error=None):
        if self._running:
            self._end_early("reject", error)
        if self.is_done:
            return
        error_str = json.dumps(error) if isinstance(error, (dict, list)) else str(error or "")
        try:
            _undo_until_anchor_gone(self.undo_anchor)
        except Exception as e:
            utils.logger.exception("Script %s rollback failed", self.id)
            error_str += f"\nRollback failed: {e}. Some script changes may remain."
        self.undo_anchor = None
        super().reject(error_str)




    def _end_early(self, kind: str, value: tp.Any):
        if self._ending is None:
            self._ending = (kind, value)
        raise _ScriptEnded



    def run(self, is_active: tp.Callable[[], bool], on_waiting: tp.Callable[[], None]):
        try:
            compiled = compile(self.code, "<ai_script>", "exec")
        except SyntaxError as e:
            self.reject(f"SyntaxError: {e}")
            return

        if not confirm.needs_asking(self.permissions):
            if self.permissions:
                utils.logger.info("Script %s runs without asking (allowed): %s", self.id, ", ".join(self.permissions))
            self._execute(compiled)
            return

        if confirm.is_asking():
            self.reject(confirm.SCRIPT.busy)
            return
        on_waiting()
        confirm.ask(
            self.id,
            self.explanation,
            self.permissions,
            is_active,
            on_allow=lambda: self._execute(compiled),
            on_reject=self.reject,
        )

    def _execute(self, compiled):
        if self.is_done:
            return

        undo = bpy.context.preferences.edit
        if not undo.use_global_undo or undo.undo_steps < 2:
            self.reject("Scripts require Global Undo and at least two undo steps in Blender preferences.")
            return

        bpy.ops.ed.undo_push(message="Exciton.ScriptStep")
        self.undo_anchor = _get_undo_anchor().name


        code = self.code if len(self.code) <= _LOGGED_SCRIPT_CHARS else self.code[:_LOGGED_SCRIPT_CHARS] + "\n[cut]"
        utils.logger.debug("Script %s:\n%s", self.id, code)

        namespace = {
            "bpy": bpy,
            "print": self.write,
            "log": self.write,
            "resolve": self.resolve,
            "reject": self.reject,
        }

        error: Exception | None = None
        self._running = True
        try:
            exec(compiled, namespace)
        except _ScriptEnded:
            pass
        except Exception as e:
            error = e
        finally:
            self._running = False

        if error is not None:
            utils.logger.info("Script %s failed", self.id, exc_info=error)

        if self._ending is not None:
            kind, value = self._ending
            if kind == "resolve":
                self.resolve(value)
            else:
                self.reject(value)
        elif error is not None:
            self.reject(f"{type(error).__name__}: {error}")
        elif not self.is_async:
            self.resolve()




    def _build_reply(self, result: str | None = None, error: str | None = None) -> td.SummonResponse:
        result, room, result_cut = _fit(result, MAX_REPLY_CHARS)
        error, room, error_cut = _fit(error, room)
        reply = super()._build_reply(result=result, error=error)
        reply["logs"], logs_cut = _fit_logs(self.logs, room)
        if result_cut or error_cut or logs_cut or self._logs_cut:
            reply["truncated"] = True
        return reply



def _fit(text: str | None, room: int) -> tuple[str | None, int, bool]:
    if text is None:
        return text, room, False
    length = _length(text)
    if length <= room:
        return text, room - length, False
    return _head(text, room), 0, True



def _fit_logs(logs: list[str], room: int) -> tuple[list[str], bool]:
    kept: list[str] = []
    for entry in logs:
        cost = _length(entry) + 1
        if cost > room:
            if room > 1:
                kept.append(_head(entry, room - 1))
            return kept, True
        kept.append(entry)
        room -= cost
    return kept, False



def _length(text: str) -> int:
    return len(text) if text.isascii() else len(text.encode("utf-16-le", "surrogatepass")) // 2



def _head(text: str, units: int) -> str:
    if text.isascii():
        return text[:units]
    head = text.encode("utf-16-le", "surrogatepass")[: units * 2].decode("utf-16-le", "surrogatepass")
    return head[:-1] if head and "\ud800" <= head[-1] <= "\udbff" else head





_ANCHOR_PREFIX = ".excitonanchor__"

_ANCHOR_MAX_AGE = 60 * 60


def _get_undo_anchor():

    now = int(time.time())
    for ng in list(bpy.data.node_groups):
        if ng.name.startswith(_ANCHOR_PREFIX):

            created = ng.name.removeprefix(_ANCHOR_PREFIX).split(".")[0]
            if not created.isdigit() or now - int(created) > _ANCHOR_MAX_AGE:
                bpy.data.node_groups.remove(ng)
    return bpy.data.node_groups.new(f"{_ANCHOR_PREFIX}{now}", tp.cast(tp.Any, "ShaderNodeTree"))


def _undo_until_anchor_gone(anchor: str | None):
    if anchor is None:
        return


    bpy.ops.ed.undo_push(message="Exciton.ScriptFailed")
    for _ in range(bpy.context.preferences.edit.undo_steps):
        if not bpy.ops.ed.undo.poll():
            break
        if "FINISHED" not in bpy.ops.ed.undo():
            break
        if anchor not in bpy.data.node_groups:

            bpy.ops.ed.undo_push(message="Exciton.ScriptRollback")
            return
    raise RuntimeError("The script's starting state is no longer available in undo history")


def _clear_anchor(anchor: str | None):
    if anchor is None:
        return
    node_group = bpy.data.node_groups.get(anchor)
    if node_group is not None:
        bpy.data.node_groups.remove(node_group)



class ScriptRunner:

    def __init__(self, is_active: tp.Callable[[], bool]):
        self._is_active = is_active


    def run(
        self,
        msg: td.FromServerMessage,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        on_waiting: tp.Callable[[], None],
    ):
        summon = SummonScript.start(msg, on_resolve=on_resolve)
        if summon:
            summon.run(self._is_active, on_waiting)
        else:
            on_resolve({"status": "ERROR", "error": "Invalid tool request", "logs": []})
