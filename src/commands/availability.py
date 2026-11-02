import re
import typing as tp
from time import perf_counter
import bpy
from .. import configs
from .. import utils
from . import context as command_context








TICK_BUDGET_SECONDS = 0.004

_UI_BASES = {"wm.call_menu": "Menu", "wm.call_menu_pie": "Menu", "wm.call_panel": "Panel", "wm.call_asset_shelf_popover": "AssetShelf"}

_PATH_STEP = re.compile(r"""\.?([A-Za-z_]\w*)|\[(\d+)\]|\[(["'])(.*?)\3\]""")

Reason: tp.TypeAlias = tp.Literal["missing", "unavailable"]



_parsed: dict[str, tuple[tp.Any, str, str]] = {}


def _parse(check: str) -> tuple[tp.Any, str, str]:
    parsed = _parsed.get(check)
    if parsed is None:
        operator, _, arg = check.partition(":")
        module, name = operator.split(".", 1)
        parsed = _parsed[check] = (getattr(getattr(bpy.ops, module), name), operator, arg)
    return parsed




def check(check: str) -> Reason | None:
    operator = check.partition(":")[0]
    try:
        op, operator, arg = _parse(check)
        if not op.poll():
            return "unavailable"
    except ValueError:
        return "missing"
    except AttributeError as e:

        if "could not be found" in str(e):
            return "missing"

        utils.logger.debug("Poll of %s failed: %s: %s", operator, type(e).__name__, e)
        return None
    except Exception as e:
        utils.logger.debug("Poll of %s failed: %s: %s", operator, type(e).__name__, e)
        return None

    if not arg:
        return None
    try:
        if operator in _UI_BASES:
            return None if _ui_type_polls(arg, getattr(bpy.types, _UI_BASES[operator])) else "unavailable"
        if operator.startswith("wm.context_"):
            return None if _path_exists(arg) else "unavailable"
        if operator == "node.add_node":
            return None if _node_type_fits(arg) else "unavailable"
    except Exception as e:
        utils.logger.debug("Check %s failed: %s: %s", check, type(e).__name__, e)
    return None


def _ui_type_polls(name: str, base: type) -> bool:
    cls = getattr(bpy.types, name, None)
    if cls is None:

        return True
    for klass in cls.__mro__:
        if klass is base:
            break
        if "poll" in vars(klass):
            return bool(cls.poll(bpy.context))
    return True




_node_fits: dict[tuple[str, str], bool] = {}


def _node_type_fits(node_type: str) -> bool:
    tree_type = getattr(bpy.context.space_data, "tree_type", None)
    if not tree_type:
        return True
    key = (tree_type, node_type)
    if key not in _node_fits:
        tree = bpy.data.node_groups.new("Exciton node check", tree_type)
        try:
            tree.nodes.new(node_type)
            _node_fits[key] = True
        except RuntimeError:
            _node_fits[key] = False
        finally:
            bpy.data.node_groups.remove(tree)
    return _node_fits[key]



def _path_exists(path: str) -> bool:
    value: tp.Any = bpy.context
    pos = 0
    while pos < len(path):
        step = _PATH_STEP.match(path, pos)
        if not step:

            return True
        attr, index, _, key = step.groups()
        try:
            if attr:
                value = getattr(value, attr)
            elif index is not None:
                value = value[int(index)]
            else:
                value = value[key]
        except (AttributeError, IndexError, KeyError, TypeError):
            return False
        pos = step.end()
    return True





class AvailabilityCheck:
    def __init__(self, context: command_context.CommandContext):
        snapshot = configs.get_config().get("_active_snapshot") or {}
        per_keymap: dict[str, list[str]] = snapshot.get("commandChecks") or {}

        self._checks = list(dict.fromkeys(c for keymap in context["active_keymaps"] for c in per_keymap.get(keymap, [])))
        self._next = 0
        self._unavailable: list[str] = []
        self._context = context
        self._spent = 0.0
        if self._checks:
            utils.set_timeout(self._tick, 0)

    def finish(self) -> list[str]:
        self._run()
        return self._unavailable

    def _tick(self):
        self._run(perf_counter() + TICK_BUDGET_SECONDS)
        if self._next < len(self._checks):
            utils.set_timeout(self._tick, 0)

    def _run(self, deadline: float | None = None):
        if self._next >= len(self._checks):
            return
        started = perf_counter()
        try:
            with bpy.context.temp_override(**command_context.override_kwargs(self._context)):
                while self._next < len(self._checks):
                    c = self._checks[self._next]
                    self._next += 1
                    if check(c):
                        self._unavailable.append(c)
                    if deadline and perf_counter() >= deadline:
                        break
        except Exception:

            utils.logger.warning("Command availability check stopped", exc_info=True)
            self._next = len(self._checks)
        self._spent += perf_counter() - started
        if self._next >= len(self._checks):
            utils.logger.debug(
                "Checked %d commands in %.1f ms: %d unavailable (%s)",
                len(self._checks),
                self._spent * 1000,
                len(self._unavailable),
                _where(self._context),
            )



def _where(context: command_context.CommandContext) -> str:
    try:
        area = context["area"].type if context["area"] else None
        region = context["region"].type if context["region"] else None
    except ReferenceError:
        return "closed since"
    pressed = context["pressed_region"]
    return f"{area}/{region}" + (f", pressed over {pressed}" if pressed != region else "")
