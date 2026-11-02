"""Read a command's actual result in Blender, without changing how its operator runs."""

import typing as tp


class Feedback(tp.NamedTuple):
    text: str
    state: bool | None = None


Reader = tp.Callable[[tp.Any], Feedback]
PROPERTY_OPERATORS = {"wm.context_toggle", "wm.context_toggle_enum", "wm.context_set_boolean"}


_PROPERTY_NAMES = {
    "tool_settings.use_snap": "Snap",
    "tool_settings.use_proportional_edit": "Proportional",
    "tool_settings.use_proportional_connected": "Proportional Connected",
    "tool_settings.use_proportional_edit_objects": "Proportional",
    "tool_settings.use_transform_data_origin": "Only Origins",
    "tool_settings.use_transform_pivot_point_align": "Only Locations",
    "tool_settings.use_transform_skip_children": "Only Parents",
    "space_data.show_gizmo": "Gizmo",
    "space_data.overlay.show_overlays": "Overlay",
}



_INVERTED_PROPERTY_NAMES = {
    "space_data.show_object_select_mesh": "Lock Mesh",
    "space_data.show_object_select_camera": "Lock Camera",
    "space_data.show_object_select_light": "Lock Light",
    "space_data.show_object_select_empty": "Lock Empty",
    "space_data.show_object_select_armature": "Lock Armature",
}


def _boolean(name: str, value: bool) -> Feedback:
    return Feedback(f"{name}: {'On' if value else 'Off'}", state=value)


def _enum_name(owner: tp.Any, prop: str) -> str:
    value = getattr(owner, prop)
    return owner.bl_rna.properties[prop].enum_items[value].name


def _view(context: tp.Any) -> Feedback:

    return Feedback(f"View: {_enum_name(context.region_data, 'view_perspective')}")


def _xray(context: tp.Any) -> Feedback:
    space = context.space_data
    obj = context.active_object
    if obj and (obj.mode == "POSE" or (obj.mode == "WEIGHT_PAINT" and obj.find_armature() is not None)):
        return _boolean("Bone X-Ray", space.overlay.show_xray_bone)
    value = space.shading.show_xray_wireframe if space.shading.type == "WIREFRAME" else space.shading.show_xray
    result = _boolean("X-Ray", value)
    if space.shading.type not in {"WIREFRAME", "SOLID"} and not (obj and obj.mode == "EDIT"):

        return Feedback(result.text + " (inactive in this shading mode)")
    return result


def _snap(context: tp.Any) -> Feedback:
    tool_settings = context.tool_settings
    items = tool_settings.bl_rna.properties["snap_elements"].enum_items
    targets = ", ".join(item.name for item in items if item.identifier in tool_settings.snap_elements)
    return Feedback(f"Snap: {targets}" if tool_settings.use_snap else f"Snap: Off ({targets})", state=tool_settings.use_snap)


def _full_area(name: str) -> Reader:



    def read(context: tp.Any) -> Feedback:
        screen = context.window.screen if context.window else context.screen
        return _boolean(name, screen.show_fullscreen)

    return read


_READERS: dict[str, Reader] = {
    "view3d.toggle_shading": lambda ctx: Feedback(f"Shading: {_enum_name(ctx.space_data.shading, 'type')}"),
    "view3d.toggle_xray": _xray,
    "view3d.view_persportho": _view,
    "view3d.view_camera": _view,
    "view3d.localview": lambda ctx: _boolean("Local View", ctx.space_data.local_view is not None),
    "screen.region_quadview": lambda ctx: _boolean("Quad View", bool(ctx.space_data.region_quadviews)),
    "exciton.bespoke_set_mode": lambda ctx: Feedback(_enum_name(ctx.active_object, "mode")),
    "exciton.bespoke_snap_to": _snap,
    "clip.lock_selection_toggle": lambda ctx: _boolean("Lock to Selection", ctx.space_data.lock_selection),
    "sculpt.dynamic_topology_toggle": lambda ctx: _boolean("Dyntopo", ctx.sculpt_object.use_dynamic_topology_sculpting),
}


def reader(operator: str, props: dict[str, tp.Any], label: str) -> Reader | None:
    """Select before invocation; read afterward, inside the command's context override.

    An unknown operator keeps its normal label-only feedback. Don't infer a state from the
    operator name or the requested value: even FINISHED operators can leave it unchanged.
    """
    if operator == "screen.screen_full_area":

        return _full_area("Focus Mode" if props.get("use_hide_panels") else "Maximize")
    if operator in PROPERTY_OPERATORS:
        path = props.get("data_path")

        if not isinstance(path, str) or not path or props.get("module"):
            return None

        def property_state(context):
            value = context.path_resolve(path)
            if path in _INVERTED_PROPERTY_NAMES and isinstance(value, bool):
                return _boolean(_INVERTED_PROPERTY_NAMES[path], not value)
            name = _PROPERTY_NAMES.get(path, label)
            if isinstance(value, bool):
                return _boolean(name, value)
            if isinstance(value, str):
                owner_path, _, prop = path.rpartition(".")
                owner = context.path_resolve(owner_path) if owner_path else context
                return Feedback(f"{name}: {_enum_name(owner, prop)}")
            raise ValueError("No boolean or enum state to report")

        return property_state
    return _READERS.get(operator)
