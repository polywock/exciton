






import typing as tp
from time import monotonic
import bpy
from ...commands import context as command_context
from . import base
from . import confirm
from . import script
from .. import td


MAX_RESULT_CHARS = 80


def _request_code(request: td.SummonCommandScriptRequest) -> str | None:
    code = request.get("script")
    if not isinstance(code, str) or not code.strip():
        return None
    return code


def _label(request: td.SummonCommandScriptRequest) -> str:
    label = request.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else "Script command"




def _sent_review(request: td.SummonCommandScriptRequest) -> tuple[bool, dict | None]:
    return "review" in request, confirm.parse_review(request.get("review"))




def _review_to_show(code: str, sent: tuple[bool, dict | None]) -> tuple[bool, dict | None]:
    was_sent, review = sent
    if was_sent:
        if review:
            confirm.keep_review(code, review)
        return True, review
    cached = confirm.cached_review(code)
    return cached is not None, cached


def _ask_for_review(summon: base.SummonBase):
    summon.status = "resolved"
    summon._on_resolve({"status": "NEEDS_REVIEW", "logs": []})




class SummonCommandScript(script.SummonScript):
    def __init__(
        self,
        id: str,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        code: str,
        label: str,
        context: command_context.CommandContext | None,

        on_ran: tp.Callable[[float, float], None] | None = None,
        sent_review: tuple[bool, dict | None] = (False, None),
    ):
        super().__init__(code, False, id, on_resolve)
        self.label = label
        self.context = context
        self._on_ran = on_ran
        self._sent_review = sent_review

    @classmethod
    def start(
        cls,
        msg: td.FromServerMessage,
        context: command_context.CommandContext | None,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        on_ran: tp.Callable[[float, float], None] | None = None,
    ) -> "SummonCommandScript | None":
        request: td.SummonCommandScriptRequest | None = msg.get("summon_request")
        id = msg.get("summon_id")
        code = _request_code(request) if request and id else None
        if not request or not id or not code:
            return None
        return cls(id, on_resolve, code, _label(request), context, on_ran, _sent_review(request))

    def run(self, is_active: tp.Callable[[], bool], on_waiting: tp.Callable[[], None]):
        try:
            compiled = compile(self.code, "<command_script>", "exec")
        except SyntaxError as e:
            self.reject(f"SyntaxError: {e}")
            return
        if confirm.is_approved(self.code):
            self._execute(compiled)
            return
        if confirm.is_asking():
            self.reject(f"“{self.label}” didn't run: {confirm.COMMAND_SCRIPT_RUN.busy}")
            return
        has_review, review = _review_to_show(self.code, self._sent_review)
        if not has_review:
            _ask_for_review(self)
            return

        if review is None:
            self.reject(f"“{self.label}” didn't run: it couldn't be checked. Try again in a moment.")
            return
        on_waiting()

        confirm.ask(
            self.id,
            "",
            [],
            is_active,
            on_allow=lambda: self._execute(compiled),
            on_reject=lambda reason: self.reject(f"“{self.label}” didn't run: {reason}"),
            kind=confirm.COMMAND_SCRIPT_RUN,
            code=self.code,
            review=review,
        )

    def _execute(self, compiled):
        started = monotonic()
        try:
            with bpy.context.temp_override(**command_context.override_kwargs(self.context)):
                super()._execute(compiled)
        finally:
            if self._on_ran:
                self._on_ran(started, monotonic())



    def resolve(self, result=None):
        text = str(result).strip()[:MAX_RESULT_CHARS] if result is not None else ""
        super().resolve(text or self.label)

    def reject(self, error=None):
        text = str(error).strip() if error is not None else ""
        if not text.startswith(f"“{self.label}” "):
            text = f"“{self.label}” failed: {text}" if text else f"“{self.label}” failed."
        super().reject(text)
