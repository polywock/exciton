







import hashlib
import json
import os
import sys
import time
import typing as tp
import bpy
from .. import configs
from .. import utils


MAX_OPERATORS = 1000
MAX_PROPS = 64
MAX_ENUM_ITEMS = 200
MAX_LABEL = 128
MAX_DESCRIPTION = 500
MAX_STRING_DEFAULT = 1024
MAX_VECTOR = 32

MAX_REPORT_BYTES = 900_000

REPORT_DELAY_SECONDS = 3


BOOL, STR, INT, FLOAT, ENUM, OBJ, FLOATVEC, INTVEC, BOOLVEC, ENUMSET = range(1, 11)


_OWN_PACKAGE = __name__.rsplit(".src.", 1)[0]

_is_addon: dict[str, bool] = {}

_reported: tuple[str, str] | None = None



def ops_name(bl_idname: str) -> str:
    if "_OT_" in bl_idname:
        module, name = bl_idname.split("_OT_", 1)
        return f"{module.lower()}.{name}"
    return bl_idname


def _rna_name(op_id: str) -> str:
    module, name = op_id.split(".", 1)
    return f"{module.upper()}_OT_{name}"



def _system_scripts() -> str:
    return os.path.normcase(os.path.realpath(bpy.utils.system_resource("SCRIPTS")))



def _class_is_addon(cls: tp.Any, system_scripts: str) -> bool:
    module_name = getattr(cls, "__module__", "") or ""
    if module_name == _OWN_PACKAGE or module_name.startswith(_OWN_PACKAGE + "."):
        return False
    path = getattr(sys.modules.get(module_name), "__file__", None)
    if not path:
        return False
    path = os.path.normcase(os.path.realpath(path))
    return not (path == system_scripts or path.startswith(system_scripts + os.sep))




def is_addon_operator(op_id: str) -> bool:
    known = _is_addon.get(op_id)
    if known is not None:
        return known
    try:
        cls = bpy.types.Operator.bl_rna_get_subclass_py(_rna_name(op_id))
    except Exception:
        cls = None
    result = cls is not None and _class_is_addon(cls, _system_scripts())
    _is_addon[op_id] = result
    return result



def addon_name(op_id: str) -> str:
    try:
        cls = bpy.types.Operator.bl_rna_get_subclass_py(_rna_name(op_id))
    except Exception:
        cls = None
    return _addon_name_of(cls) if cls else op_id.split(".", 1)[0]


def _addon_name_of(cls: tp.Any) -> str:
    module_name = getattr(cls, "__module__", "") or ""
    for mod in _addon_modules():
        if module_name == mod.__name__ or module_name.startswith(mod.__name__ + "."):
            try:
                import addon_utils

                name = addon_utils.module_bl_info(mod).get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()[:MAX_LABEL]
            except Exception:
                utils.logger.debug("No add-on info for %s", mod.__name__, exc_info=True)
            return mod.__name__.rsplit(".", 1)[-1][:MAX_LABEL]
    return module_name.split(".")[0][:MAX_LABEL] or "Unknown"


def _addon_modules() -> list[tp.Any]:
    try:
        import addon_utils

        return list(addon_utils.modules(refresh=False))
    except Exception:
        return []


def _registered_operator_classes() -> list[tp.Any]:
    seen: list[tp.Any] = []
    stack = list(bpy.types.Operator.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if getattr(cls, "is_registered", False) and getattr(cls, "bl_idname", None):
            seen.append(cls)
    return seen


def _round(value: tp.Any) -> tp.Any:
    return round(value, 6) if isinstance(value, float) else value



def prop_entry(p: tp.Any) -> dict | None:
    if p.identifier == "rna_type" or getattr(p, "is_hidden", False):
        return None
    kind = p.type
    size = getattr(p, "array_length", 0) or 0
    entry: dict[str, tp.Any] = {"key": p.identifier, "label": (p.name or p.identifier)[:MAX_LABEL]}
    if kind in ("BOOLEAN", "INT", "FLOAT"):
        if size:
            if size > MAX_VECTOR:
                return None
            entry["type"] = {"BOOLEAN": BOOLVEC, "INT": INTVEC, "FLOAT": FLOATVEC}[kind]
            entry["size"] = size
            entry["defaultValue"] = [_round(v) for v in p.default_array]
        else:
            entry["type"] = {"BOOLEAN": BOOL, "INT": INT, "FLOAT": FLOAT}[kind]
            entry["defaultValue"] = _round(p.default)
    elif kind == "STRING":
        entry["type"] = STR
        entry["defaultValue"] = (p.default or "")[:MAX_STRING_DEFAULT]
    elif kind == "ENUM":
        items = [{"key": i.identifier[:64], "label": (i.name or i.identifier)[:MAX_LABEL]} for i in p.enum_items]
        if not items:
            return None
        flag = p.is_enum_flag
        entry["type"] = ENUMSET if flag else ENUM
        entry["enum"] = items[:MAX_ENUM_ITEMS]
        entry["defaultValue"] = sorted(p.default_flag) if flag else p.default
    else:
        return None
    if getattr(p, "is_required", False):
        entry["required"] = True
    return entry



def discover() -> list[dict]:
    system_scripts = _system_scripts()
    found: dict[str, dict] = {}
    for cls in _registered_operator_classes():
        if not _class_is_addon(cls, system_scripts):
            continue
        op_id = ops_name(cls.bl_idname)
        if op_id in found or "." not in op_id:
            continue
        try:
            module, name = op_id.split(".", 1)
            rna = getattr(getattr(bpy.ops, module), name).get_rna_type()
        except Exception:
            utils.logger.debug("Couldn't describe %s", op_id, exc_info=True)
            continue
        props = [entry for p in rna.properties if (entry := prop_entry(p))][:MAX_PROPS]
        op: dict[str, tp.Any] = {
            "key": op_id,
            "label": (rna.name or getattr(cls, "bl_label", "") or op_id)[:MAX_LABEL],
            "addon": _addon_name_of(cls),
        }
        if rna.description:
            op["description"] = rna.description[:MAX_DESCRIPTION]
        if props:
            op["props"] = props
        found[op_id] = op
    return sorted(found.values(), key=lambda op: op["key"])[:MAX_OPERATORS]



def fit(operators: list[dict], budget: int) -> tuple[list[dict], int]:
    kept: list[dict] = []
    used = len('{"operators":[]}')
    for op in operators:
        size = len(json.dumps(op, separators=(",", ":"), sort_keys=True).encode()) + 1
        if used + size > budget:
            continue
        kept.append(op)
        used += size
    return kept, len(operators) - len(kept)




def report_soon():
    utils.set_timeout(_report, REPORT_DELAY_SECONDS)


def _report():
    token = configs.get_config().get("token")
    if not token:
        return
    started = time.perf_counter()
    try:
        operators = discover()
    except Exception:
        utils.logger.warning("Couldn't list add-on operators", exc_info=True)
        return

    utils.logger.info("Listed %d add-on operators in %.0f ms", len(operators), (time.perf_counter() - started) * 1000)
    operators, left_out = fit(operators, MAX_REPORT_BYTES)
    if left_out:
        utils.logger.warning("%d add-on operators left out of the report, which would be too large", left_out)
    body = json.dumps({"operators": operators}, separators=(",", ":"), sort_keys=True)
    key = (hashlib.sha256(token.encode()).hexdigest(), hashlib.sha256(body.encode()).hexdigest())
    if _reported == key:
        return
    from ..api import addon_operators as api

    def done():
        global _reported
        _reported = key

    utils.logger.info("Reporting %d add-on operators", len(operators))
    api.report(token, body, on_done=done)
