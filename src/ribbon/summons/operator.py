import json
import typing as tp
from time import monotonic
import bpy
from ... import utils
from ...commands import addon_operators
from ...commands import availability
from ...commands import feedback
from ...commands import guard
from ...commands import context as command_context
from . import base
from . import confirm
from .. import td



class SummonOperator(base.SummonBase):
    def __init__(
        self,
        id: str,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        request: td.SummonOperatorRequest,
        context: command_context.CommandContext | None,

        on_ran: tp.Callable[[float, float], None] | None = None,
    ):
        super().__init__(id, on_resolve)
        self._on_ran = on_ran
        self.operator = request.get("operator", "")

        self.props = {
            key: value for p in request.get("props") or [] if (key := p.get("key")) and (value := p.get("value")) is not None
        }
        self.label = request.get("label") or self.operator

        self.check = request.get("check") or self.operator
        self.context = context
        self._feedback = feedback.reader(self.operator, self.props, self.label)

    @classmethod
    def start(
        cls,
        msg: td.FromServerMessage,
        context: command_context.CommandContext | None,
        on_resolve: tp.Callable[[td.SummonResponse], None],
        on_ran: tp.Callable[[float, float], None] | None = None,
    ) -> "SummonOperator | None":
        request: td.SummonOperatorRequest | None = msg.get("summon_request")
        id = msg.get("summon_id")
        if not request or not id or not request.get("operator"):
            return None
        return cls(id, on_resolve, request, context, on_ran)




    def run(self, is_active: tp.Callable[[], bool] = lambda: True, on_waiting: tp.Callable[[], None] = lambda: None):
        if reason := guard.refusal(self.operator, self.props):
            utils.logger.warning("Refused a voice command: %s", reason)
            self.reject(f"“{self.label}” can't run from a voice command")
            return
        try:
            with bpy.context.temp_override(**command_context.override_kwargs(self.context)):
                reason = availability.check(self.check)
        except Exception as e:
            utils.logger.warning("Checking %s failed", self.check, exc_info=True)
            self.reject(f"“{self.label}” failed: {e}")
            return
        if reason == "missing":
            self.reject(f"Blender has no “{self.label}” command")
            return
        if reason == "unavailable":
            self.reject(f"“{self.label}” isn't available here")
            return

        module, name = self.operator.split(".", 1)
        op = getattr(getattr(bpy.ops, module), name)

        if addon_operators.is_addon_operator(self.operator) and not confirm.is_approved(self._approve_key()):
            self._ask(op, is_active, on_waiting)
            return
        self._go(op)

    def _go(self, op):
        if self._feedback is None:
            self.resolve(self.label)



        utils.set_timeout(lambda: self._invoke(op), 0)


    def _approve_key(self) -> str:
        return "operator:" + json.dumps({"operator": self.operator, "props": self.props}, sort_keys=True, default=str)

    def _ask(self, op, is_active: tp.Callable[[], bool], on_waiting: tp.Callable[[], None]):
        if confirm.is_asking():
            self.reject(f"“{self.label}” didn't run: {confirm.ADDON_OPERATOR.busy}")
            return
        on_waiting()
        confirm.ask(
            self.id,
            "",
            [],
            is_active,
            on_allow=lambda: self._go(op),
            on_reject=lambda reason: self.reject(f"“{self.label}” didn't run: {reason}"),
            kind=confirm.ADDON_OPERATOR,
            operator=_describe(op, self.operator, self.props),
            approve_key=self._approve_key(),
        )

    def _invoke(self, op):
        started = monotonic()
        try:
            with bpy.context.temp_override(**command_context.override_kwargs(self.context)):


                result = op("INVOKE_DEFAULT", True, **_blender_props(op, self.props))
                if self._on_ran:
                    self._on_ran(started, monotonic())
                if self._feedback is not None:
                    if "CANCELLED" in result and self.operator not in feedback.PROPERTY_OPERATORS:
                        self.reject(f"“{self.label}” was cancelled.")
                    elif "FINISHED" in result or "CANCELLED" in result:


                        try:
                            observed = self._feedback(bpy.context)
                        except Exception:

                            utils.logger.debug("Reading state for %s failed", self.operator, exc_info=True)
                            observed = feedback.Feedback(f"{self.label}: state unavailable")
                        self.resolve(observed.text, state=observed.state)
                    elif "PASS_THROUGH" in result:
                        self.reject(f"“{self.label}” didn't run.")
                    else:

                        self.resolve(self.label)
        except Exception as e:
            utils.logger.warning("Operator %s failed with props %s", self.operator, self.props, exc_info=True)
            if self._feedback is not None:
                self.reject(f"“{self.label}” failed: {e}")
            return
        if "CANCELLED" in result and self.operator not in feedback.PROPERTY_OPERATORS:
            utils.logger.info("Operator %s cancelled", self.operator)




def _describe(op, operator: str, props: dict[str, tp.Any]) -> dict:
    try:
        rna = op.get_rna_type()
        label, description, rna_props = rna.name or operator, rna.description, rna.properties
    except Exception:
        label, description, rna_props = operator, "", {}
    options = []
    for key, value in props.items():
        prop = rna_props.get(key) if hasattr(rna_props, "get") else None
        subtype = getattr(prop, "subtype", "")
        is_path = subtype in ("FILE_PATH", "DIR_PATH", "FILE_NAME") or any(w in key.lower() for w in ("path", "file", "dir"))
        options.append((getattr(prop, "name", "") or key, _shown(value), is_path))
    return {
        "key": operator,
        "label": label,
        "addon": addon_operators.addon_name(operator),
        "description": description,
        "options": options,
    }


def _shown(value: tp.Any) -> str:
    if isinstance(value, str):
        text = f"“{value}”"
    elif isinstance(value, (list, tuple, set)):
        text = ", ".join(str(v) for v in value)
    else:
        text = str(value)
    return text if len(text) <= 120 else text[:119] + "…"




def _blender_props(op, props: dict[str, tp.Any]) -> dict[str, tp.Any]:
    rna = op.get_rna_type().properties
    return {
        key: set(value) if isinstance(value, list) and key in rna and getattr(rna[key], "is_enum_flag", False) else value
        for key, value in props.items()
    }
