import contextlib
import typing as tp
import bpy
from .. import utils
from . import keymaps

if tp.TYPE_CHECKING:
    from ..ribbon import td




class CommandContext(tp.TypedDict):
    window: tp.Any
    area: tp.Any

    region: tp.Any

    pressed_region: str | None

    active_keymaps: list[str]

    description: dict[str, str]


def capture() -> CommandContext:
    ctx = bpy.context
    pressed = ctx.region
    region = _main_region(ctx.area, pressed)
    active: list[str] = []


    with bpy.types.Context.temp_override(ctx, region=region) if region != pressed else contextlib.nullcontext():
        for keymap in keymaps.keymaps:
            try:
                if keymap.poll():
                    active.append(keymap.key)
            except Exception:
                utils.logger.warning("Keymap poll failed: %s", keymap.key, exc_info=True)
    return {
        "window": ctx.window,
        "area": ctx.area,
        "region": region,
        "pressed_region": pressed.type if pressed else None,
        "active_keymaps": active,
        "description": _describe(ctx),
    }







CONTENT_REGIONS = ("WINDOW", "CHANNELS", "PREVIEW")


def _main_region(area: tp.Any, region: tp.Any) -> tp.Any:
    if area is None or region is None or region.type in CONTENT_REGIONS:
        return region


    space = area.spaces.active
    shows_preview_only = (area.type == "SEQUENCE_EDITOR" and getattr(space, "view_type", None) == "PREVIEW") or (
        area.type == "CLIP_EDITOR" and getattr(space, "view", None) in ("GRAPH", "DOPESHEET")
    )
    main_type = "PREVIEW" if shows_preview_only else "WINDOW"
    if keymaps.has_own_keymaps(area.type, region.type, main_type):
        return region
    mains = [r for r in area.regions if r.type == main_type]

    own = getattr(space, "region_3d", None)

    return next((r for r in mains if own is not None and r.data == own), mains[0] if mains else region)



def prelim_fields(context: CommandContext) -> "td.Prelim":
    return {"activeKeymaps": context["active_keymaps"], "commandContext": context["description"]}



def _describe(ctx: bpy.types.Context) -> dict[str, str]:
    description: dict[str, str] = {}
    area = ctx.area
    if area:

        description["editor"] = _enum_name(area, "ui_type") or _enum_name(area, "type") or area.type
    obj = ctx.active_object
    if obj:
        description["mode"] = _enum_name(obj, "mode") or obj.mode
        description["objectType"] = _enum_name(obj, "type") or obj.type
    return description


def _enum_name(struct: tp.Any, prop: str) -> str | None:
    try:
        return struct.bl_rna.properties[prop].enum_items[getattr(struct, prop)].name
    except Exception:
        return None



def override_kwargs(context: CommandContext | None) -> dict[str, tp.Any]:
    if not context:
        return {}
    kwargs: dict[str, tp.Any] = {}
    for key in ("window", "area", "region"):
        value = context.get(key)
        try:

            if value is not None and value.as_pointer():
                kwargs[key] = value
        except ReferenceError:
            pass
    return kwargs
