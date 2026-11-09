






import json
import typing as tp
import bpy
from .. import configs
from .. import utils
from .. import windows
from ..api import button_command
from . import addon_operators
from . import context as command_context

SETTINGS_ACTION = "exciton.action"
MAX_LABEL = 128

MAX_ALIASES_SHOWN = 4
FLOAT_DIGITS = 6

_SKIPPED_TYPES = ("POINTER", "COLLECTION")

_SPACE_PARTS = ("overlay", "shading", "uv_editor", "dopesheet", "params", "preview_overlay", "timeline_overlay", "cache_overlay")

_OBJECT_MEMBERS = (
    "edit_object",
    "pose_object",
    "sculpt_object",
    "vertex_paint_object",
    "weight_paint_object",
    "image_paint_object",
    "object",
)



def _json_value(value: tp.Any) -> tp.Any:
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return [_json_value(v) for v in value]


def _set_properties(op: tp.Any) -> list[tp.Any]:
    return [
        p
        for p in op.bl_rna.properties
        if p.identifier != "rna_type" and not p.is_hidden and p.type not in _SKIPPED_TYPES and op.is_property_set(p.identifier)
    ]



def read_props(op: tp.Any) -> dict[str, tp.Any]:
    return {p.identifier: _json_value(getattr(op, p.identifier)) for p in _set_properties(op)}




def suggested_label(op: tp.Any) -> str:
    words = [op.bl_rna.name]
    for p in _set_properties(op):
        if p.type == "ENUM" and not p.is_enum_flag:
            value = getattr(op, p.identifier)
            words.append(next((item.name for item in p.enum_items if item.identifier == value), ""))
    return " ".join(word for word in words if word)[:MAX_LABEL]





def _context_path(context: tp.Any, owner: tp.Any, prop: str) -> str | None:
    space = getattr(context, "space_data", None)
    if space is not None:
        if owner == space:
            return f"space_data.{prop}"
        for part in _SPACE_PARTS:
            if getattr(space, part, None) == owner:
                return f"space_data.{part}.{prop}"
    try:
        within = owner.path_from_id()
    except ValueError:
        return None
    if "[" in within:
        return None
    member = _id_member(context, owner.id_data)
    if member is None:
        return None

    if member == "scene" and within.partition(".")[0] == "tool_settings":
        member = ""
    return ".".join(part for part in (member, within, prop) if part)


def _id_member(context: tp.Any, data: tp.Any) -> str | None:
    if data is None:
        return None
    scene = getattr(context, "scene", None)
    if scene is not None:
        if data == scene:
            return "scene"
        if data == scene.world:
            return "scene.world"
    for member in _OBJECT_MEMBERS:
        obj = getattr(context, member, None)
        if obj is None:
            continue
        if data == obj:
            return member
        if data == obj.data:
            return f"{member}.data"
        if data == obj.active_material:
            return f"{member}.active_material"
    return None


def _read_checkbox(context: tp.Any) -> dict[str, str] | None:
    prop = getattr(context, "button_prop", None)
    owner = getattr(context, "button_pointer", None)
    if prop is None or owner is None or prop.type != "BOOLEAN" or prop.is_array or prop.is_readonly:
        return None
    path = _context_path(context, owner, prop.identifier)
    if path is None:
        return None
    return {"operator_id": "wm.context_toggle", "props_json": json.dumps({"data_path": path}), "suggested": prop.name[:MAX_LABEL]}



def read_button(context: tp.Any) -> dict[str, str] | None:
    op = getattr(context, "button_operator", None)
    if op is None:
        return _read_checkbox(context)
    operator_id = addon_operators.ops_name(op.bl_rna.identifier)
    if operator_id.startswith("exciton."):
        return None
    return {"operator_id": operator_id, "props_json": json.dumps(read_props(op)), "suggested": suggested_label(op)}


def _fill(op: tp.Any, button: dict[str, str]):
    op.operator_id = button["operator_id"]
    op.props_json = button["props_json"]
    op.suggested = button["suggested"]


def _active_keymaps() -> list[str]:
    return command_context.capture()["active_keymaps"]


def _send(window: tp.Any, body: dict, draw_reply: tp.Callable[[dict], tp.Callable]) -> bool:
    token = configs.get_config().get("token")
    if not token:
        return False

    def on_reply(reply: dict | None, error: str | None, upgrade_path: str | None):
        _popup(window, draw_reply(reply) if reply is not None else _draw_refused(error or button_command.FAILED, upgrade_path))

    button_command.send(token, body, on_reply)
    return True



def _popup(window: tp.Any, draw: tp.Callable):
    if not windows.is_open(window):
        window = next(iter(windows.all_windows()), None)
    if window is None:
        return
    try:
        with bpy.context.temp_override(window=window, screen=window.screen):
            bpy.context.window_manager.popup_menu(draw, title="Exciton")
    except Exception:
        utils.logger.warning("Couldn't show the button command's result", exc_info=True)


def _website_button(layout: tp.Any, text: str, path: str):
    layout.operator_context = "INVOKE_DEFAULT"
    op = layout.operator(SETTINGS_ACTION, text=text, icon="URL")
    op.type = "OPEN_WEBSITE_PATH"
    op.target_key = path


def _draw_refusal(layout: tp.Any, text: str, upgrade_path: str | None):
    layout.label(text=text)
    if upgrade_path:
        _website_button(layout, "Upgrade", upgrade_path)


def _draw_refused(text: str, upgrade_path: str | None):
    def draw(menu, context):
        _draw_refusal(menu.layout, text, upgrade_path)

    return draw


def _other_names(aliases: list[str]) -> str:
    if not aliases:
        return ""
    names = ", ".join(f"“{alias}”" for alias in aliases[:MAX_ALIASES_SHOWN])
    more = len(aliases) - MAX_ALIASES_SHOWN
    return f" (also {names}{f', +{more} more' if more > 0 else ''})"


def describe(command: dict) -> str:
    text = f"“{command.get('label')}”{_other_names(command.get('aliases') or [])} in {command.get('keymap')}"
    if command.get("off"):
        return f"{text} (off)"
    return text if command.get("here") else f"{text} (works elsewhere)"


def _draw_commands(layout: tp.Any, commands: list[dict]):
    for command in commands:
        layout.label(text=describe(command), icon="DOT")


def _add_button(layout: tp.Any, button: dict[str, str], active: list[str], text: str):
    layout.operator_context = "INVOKE_DEFAULT"
    op = layout.operator(EXCITON_OT_add_button_command.bl_idname, text=text, icon="ADD")
    _fill(op, button)
    op.active_keymaps_json = json.dumps(active)


def _draw_check(reply: dict, button: dict[str, str], active: list[str]):
    matches = reply.get("matches") or []
    similar = reply.get("similar") or []
    has_on = any(not command.get("off") for command in matches)

    def draw(menu, context):
        layout = menu.layout
        if has_on:
            layout.label(text="You have this voice command:")
            _draw_commands(layout, matches)
            return
        if matches:
            layout.label(text="You have this voice command, but it's off:")
            _draw_commands(layout, matches)
        else:
            layout.label(text="You don't have a voice command for this.")
            if similar:
                layout.separator()
                layout.label(text="With other options:")
                _draw_commands(layout, similar)
        layout.separator()
        if refusal := reply.get("refusal"):
            _draw_refusal(layout, refusal, reply.get("upgradePath"))
        else:
            _add_button(layout, button, active, "Turn On Voice Command" if matches else "Add as Voice Command")

    return draw


_ADD_HEADINGS = {
    "ADDED": "Added {}.",
    "TURNED_ON": "Turned on {}.",
    "EXISTS": "You already have this: {}.",
}


def _draw_add(reply: dict):
    command = reply.get("command") or {}
    heading = _ADD_HEADINGS.get(reply.get("status", ""), "{}").format(describe(command))
    shared = reply.get("sharedWith") or []
    edit_path = reply.get("editPath") or "/commands"

    def draw(menu, context):
        layout = menu.layout
        layout.label(text=heading, icon="CHECKMARK")
        if shared:
            layout.separator()
            layout.label(text="Said the same way as:")
            _draw_commands(layout, shared)
        layout.separator()
        _website_button(layout, "Edit on the Website", edit_path)

    return draw


def _check(context: tp.Any, op: tp.Any) -> set[str]:
    active = _active_keymaps()
    button = {"operator_id": op.operator_id, "props_json": op.props_json, "suggested": op.suggested}
    body = {"action": "CHECK", "operator": op.operator_id, "props": json.loads(op.props_json), "activeKeymaps": active}
    if not _send(context.window, body, lambda reply: _draw_check(reply, button, active)):
        op.report({"WARNING"}, "Sign in to Exciton first")
        return {"CANCELLED"}
    return {"FINISHED"}



def _can_add() -> bool:
    return (configs.get_config().get("_active_snapshot") or {}).get("canAddCommands") is not False


class EXCITON_OT_check_button_command(bpy.types.Operator):
    bl_idname = "exciton.check_button_command"
    bl_label = "Check Voice Command"
    bl_description = "See whether you have a voice command that does what this does"
    bl_options = {"INTERNAL"}

    operator_id: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    props_json: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    suggested: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        return _check(context, self)


class EXCITON_OT_add_button_command(bpy.types.Operator):
    bl_idname = "exciton.add_button_command"
    bl_label = "Add as Voice Command"
    bl_description = "Add a voice command that does what this does, with the same options"
    bl_options = {"INTERNAL"}

    operator_id: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    props_json: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    suggested: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    active_keymaps_json: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    label: bpy.props.StringProperty(
        name="Say", description="What you say to run it", maxlen=MAX_LABEL, options={"SKIP_SAVE"}
    )

    def invoke(self, context, event):


        if not self.active_keymaps_json and not _can_add():
            return _check(context, self)
        self.label = self.suggested
        if not self.active_keymaps_json:
            self.active_keymaps_json = json.dumps(_active_keymaps())
        return context.window_manager.invoke_props_dialog(self, title="Add Voice Command", confirm_text="Add")

    def draw(self, context):
        self.layout.activate_init = True
        self.layout.prop(self, "label")

    def execute(self, context):
        if not self.label.strip():
            self.report({"WARNING"}, "Say what you'd say to run it")
            return {"CANCELLED"}
        body = {
            "action": "ADD",
            "operator": self.operator_id,
            "props": json.loads(self.props_json),
            "activeKeymaps": json.loads(self.active_keymaps_json),
            "label": self.label,
        }
        if not _send(context.window, body, _draw_add):
            self.report({"WARNING"}, "Sign in to Exciton first")
            return {"CANCELLED"}

        self.report({"INFO"}, "Adding voice command...")
        return {"FINISHED"}


class EXCITON_MT_button_command(bpy.types.Menu):
    bl_idname = "EXCITON_MT_button_command"
    bl_label = "Exciton"

    def draw(self, context):
        layout = self.layout
        button = read_button(context)
        if not button:
            return
        if not configs.get_config().get("token"):
            layout.label(text="Sign in from the Exciton panel")
            return
        layout.operator_context = "INVOKE_DEFAULT"
        _fill(layout.operator(EXCITON_OT_check_button_command.bl_idname, icon="VIEWZOOM"), button)
        _fill(layout.operator(EXCITON_OT_add_button_command.bl_idname, icon="ADD"), button)


def _draw_entry(self, context):
    if read_button(context):
        self.layout.separator()
        self.layout.menu(EXCITON_MT_button_command.bl_idname)


classes = (EXCITON_OT_check_button_command, EXCITON_OT_add_button_command, EXCITON_MT_button_command)


def register():
    utils.register(classes)
    bpy.types.UI_MT_button_context_menu.append(_draw_entry)


def unregister():
    bpy.types.UI_MT_button_context_menu.remove(_draw_entry)
    utils.unregister(classes)
