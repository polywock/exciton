














import dataclasses
import typing as tp
import bpy



Zone: tp.TypeAlias = dict[str, tp.Container[str]]


class _AnyArea:
    def __contains__(self, area_type: object) -> bool:
        return True



ANY_AREA: tp.Container[str] = _AnyArea()


def zone(*areas: str, regions: tuple[str, ...] = ("WINDOW",)) -> Zone:
    return {region: areas for region in regions}


@dataclasses.dataclass(frozen=True)
class Keymap:
    key: str

    zone: Zone | None = None


    when: tp.Callable[[], bool] | None = None

    def zone_poll(self) -> bool:
        if self.zone is None:
            return True
        area = getattr(bpy.context, "area", None)
        region = getattr(bpy.context, "region", None)
        if area is None or region is None:
            return False
        return area.type in self.zone.get(region.type, ())

    def poll(self) -> bool:
        return self.zone_poll() and (self.when is None or bool(self.when()))




VIEW_3D = zone("VIEW_3D")
IMAGE = zone("IMAGE_EDITOR")
VIEW_3D_OR_IMAGE = zone("VIEW_3D", "IMAGE_EDITOR")
NODE = zone("NODE_EDITOR")

_TOOL_HEADER_AREAS = ("VIEW_3D", "IMAGE_EDITOR", "SEQUENCE_EDITOR")
_ASSET_SHELF_AREAS = ("VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR")

REGION_CONTEXT_MENU_ZONE: Zone = {
    "HEADER": ANY_AREA,
    "FOOTER": ANY_AREA,
    "TOOL_HEADER": _TOOL_HEADER_AREAS,
    "ASSET_SHELF_HEADER": _ASSET_SHELF_AREAS,
    "WINDOW": ("TOPBAR",),
    "NAVIGATION_BAR": ("PROPERTIES",),
    "UI": ("PREFERENCES", "PROJECT"),
    "SCRUBBING": ("SEQUENCE_EDITOR",),
}

VIEW2D_ZONE: Zone = {
    "HEADER": ANY_AREA,
    "FOOTER": ANY_AREA,
    "HUD": ANY_AREA,
    "SCRUBBING": ("SEQUENCE_EDITOR",),
    "WINDOW": (
        "NODE_EDITOR",
        "GRAPH_EDITOR",
        "DOPESHEET_EDITOR",
        "NLA_EDITOR",
        "SEQUENCE_EDITOR",
        "OUTLINER",
        "FILE_BROWSER",
        "CONSOLE",
        "INFO",
        "SPREADSHEET",
        "TOPBAR",
        "SCRIPT",
    ),
    "PREVIEW": ("CLIP_EDITOR", "SEQUENCE_EDITOR"),
    "TOOL_HEADER": _TOOL_HEADER_AREAS,
    "CHANNELS": ("GRAPH_EDITOR", "DOPESHEET_EDITOR", "NLA_EDITOR"),
    "ASSET_SHELF_HEADER": _ASSET_SHELF_AREAS,
}


VIEW2D_BUTTONS_LIST_ZONE: Zone = {
    "HUD": ANY_AREA,
    "WINDOW": ("PROPERTIES", "PREFERENCES", "PROJECT", "CONSOLE", "TOPBAR", "SPREADSHEET"),
    "UI": (
        "VIEW_3D",
        "IMAGE_EDITOR",
        "NODE_EDITOR",
        "GRAPH_EDITOR",
        "DOPESHEET_EDITOR",
        "NLA_EDITOR",
        "SEQUENCE_EDITOR",
        "CLIP_EDITOR",
        "TEXT_EDITOR",
        "FILE_BROWSER",
        "SPREADSHEET",
        "PREFERENCES",
        "PROJECT",
    ),
    "TOOLS": ("VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "SEQUENCE_EDITOR", "CLIP_EDITOR", "FILE_BROWSER", "SPREADSHEET"),
    "EXECUTE": ("FILE_BROWSER", "PREFERENCES", "PROJECT"),
    "ASSET_SHELF": _ASSET_SHELF_AREAS,
    "NAVIGATION_BAR": ("PROPERTIES",),
    "TOOL_PROPS": ("FILE_BROWSER",),
}

USER_INTERFACE_ZONE: Zone = {
    "HEADER": ANY_AREA,
    "HUD": ANY_AREA,
    "SCRUBBING": ("SEQUENCE_EDITOR",),
    "WINDOW": (
        "TOPBAR",
        "PREFERENCES",
        "PROJECT",
        "SPREADSHEET",
        "OUTLINER",
        "NODE_EDITOR",
        "INFO",
        "FILE_BROWSER",
        "CONSOLE",
        "CLIP_EDITOR",
        "PROPERTIES",
        "SCRIPT",
    ),
    "TOOL_HEADER": _TOOL_HEADER_AREAS,
    "FOOTER": ("TEXT_EDITOR", "SPREADSHEET", "SEQUENCE_EDITOR", "NLA_EDITOR", "GRAPH_EDITOR", "DOPESHEET_EDITOR"),
    "UI": (
        "PREFERENCES",
        "PROJECT",
        "VIEW_3D",
        "TEXT_EDITOR",
        "SPREADSHEET",
        "SEQUENCE_EDITOR",
        "NODE_EDITOR",
        "NLA_EDITOR",
        "IMAGE_EDITOR",
        "GRAPH_EDITOR",
        "FILE_BROWSER",
        "CLIP_EDITOR",
        "DOPESHEET_EDITOR",
    ),
    "TOOLS": ("VIEW_3D", "SPREADSHEET", "SEQUENCE_EDITOR", "NODE_EDITOR", "IMAGE_EDITOR", "FILE_BROWSER", "CLIP_EDITOR"),
    "CHANNELS": ("SEQUENCE_EDITOR", "NLA_EDITOR", "GRAPH_EDITOR", "CLIP_EDITOR", "DOPESHEET_EDITOR"),
    "EXECUTE": ("PREFERENCES", "PROJECT", "FILE_BROWSER"),
    "NAVIGATION_BAR": ("PROPERTIES",),
    "ASSET_SHELF": _ASSET_SHELF_AREAS,
    "ASSET_SHELF_HEADER": _ASSET_SHELF_AREAS,
    "TOOL_PROPS": ("FILE_BROWSER",),
    "PREVIEW": ("CLIP_EDITOR",),
}

FRAMES_ZONE: Zone = {
    "WINDOW": (
        "VIEW_3D",
        "IMAGE_EDITOR",
        "NODE_EDITOR",
        "GRAPH_EDITOR",
        "DOPESHEET_EDITOR",
        "NLA_EDITOR",
        "SEQUENCE_EDITOR",
        "CLIP_EDITOR",
        "INFO",
        "PROPERTIES",
        "SPREADSHEET",
        "SCRIPT",
    ),
    "PREVIEW": ("CLIP_EDITOR", "SEQUENCE_EDITOR"),
    "HEADER": (
        "VIEW_3D",
        "IMAGE_EDITOR",
        "NODE_EDITOR",
        "GRAPH_EDITOR",
        "DOPESHEET_EDITOR",
        "NLA_EDITOR",
        "SEQUENCE_EDITOR",
        "CLIP_EDITOR",
        "INFO",
        "PROPERTIES",
        "SPREADSHEET",
    ),
    "TOOL_HEADER": _TOOL_HEADER_AREAS,
    "FOOTER": ("SPREADSHEET", "SEQUENCE_EDITOR", "NLA_EDITOR", "GRAPH_EDITOR", "DOPESHEET_EDITOR"),
    "UI": (
        "VIEW_3D",
        "IMAGE_EDITOR",
        "NODE_EDITOR",
        "GRAPH_EDITOR",
        "DOPESHEET_EDITOR",
        "NLA_EDITOR",
        "SEQUENCE_EDITOR",
        "CLIP_EDITOR",
        "SPREADSHEET",
    ),
    "TOOLS": ("VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "SEQUENCE_EDITOR", "CLIP_EDITOR", "SPREADSHEET"),
    "CHANNELS": ("GRAPH_EDITOR", "DOPESHEET_EDITOR", "NLA_EDITOR", "CLIP_EDITOR"),
    "ASSET_SHELF": _ASSET_SHELF_AREAS,
    "NAVIGATION_BAR": ("PROPERTIES",),
    "SCRUBBING": ("SEQUENCE_EDITOR",),
}

GREASE_PENCIL_ZONE: Zone = {
    "WINDOW": ("VIEW_3D", "IMAGE_EDITOR", "NODE_EDITOR", "CLIP_EDITOR"),
    "PREVIEW": ("SEQUENCE_EDITOR",),
}


ANIMATION_ZONE: Zone = {
    "WINDOW": ("GRAPH_EDITOR", "DOPESHEET_EDITOR", "NLA_EDITOR", "SEQUENCE_EDITOR"),
    "SCRUBBING": ("SEQUENCE_EDITOR",),
}





def editing(*object_types: str) -> tp.Callable[[], bool]:
    def when():
        ob = bpy.context.active_object
        return ob is not None and ob.type in object_types and ob.mode == "EDIT"

    return when


def in_mode(mode: str) -> tp.Callable[[], bool]:
    def when():
        ob = bpy.context.active_object
        return ob is not None and ob.mode == mode

    return when



def operator_polls(idname: str) -> tp.Callable[[], bool]:
    module, name = idname.split(".")
    return lambda: getattr(getattr(bpy.ops, module), name).poll()



def paint_mesh(modes: tuple[str, ...], attribute: str) -> tp.Callable[[], bool]:
    def when():
        ob = bpy.context.active_object
        if ob is None or ob.type != "MESH" or ob.mode not in modes:
            return False
        return bool(getattr(ob.data, attribute, None))

    return when



def grease_pencil_in(*modes: str, settings: str | None = None) -> tp.Callable[[], bool]:
    def when():
        ob = bpy.context.active_object
        if ob is None or ob.type != "GREASEPENCIL" or ob.mode not in modes:
            return False
        return settings is None or getattr(bpy.context.tool_settings, settings) is not None

    return when


def _no_object_or_object_mode():
    ob = bpy.context.active_object
    return not ob or ob.mode == "OBJECT"




def _image_paint():
    if bpy.context.area.type == "IMAGE_EDITOR":
        return bpy.ops.paint.image_paint.poll()
    ob = bpy.context.active_object
    return (
        ob is not None and ob.mode == "TEXTURE_PAINT" and bpy.ops.paint.texture_paint_toggle.poll()
    ) or bpy.ops.paint.image_paint.poll()



_PAINT_SETTINGS_BY_MODE = {
    "SCULPT": "sculpt",
    "VERTEX_PAINT": "vertex_paint",
    "WEIGHT_PAINT": "weight_paint",
    "TEXTURE_PAINT": "image_paint",
    "SCULPT_CURVES": "curves_sculpt",
}



def _paint_curve():
    ctx = bpy.context
    if ctx.area.type == "IMAGE_EDITOR":
        sd = ctx.space_data
        if not sd or getattr(sd, "mode", None) != "PAINT":
            return False
        paint = ctx.tool_settings.image_paint
    else:
        ob = ctx.active_object
        attr = _PAINT_SETTINGS_BY_MODE.get(ob.mode) if ob else None
        if attr is None:
            return False
        paint = getattr(ctx.tool_settings, attr, None)
    brush = paint.brush if paint else None
    return brush is not None and brush.stroke_method == "CURVE"


def _gp_brush_type(brush):

    return getattr(brush, "gpencil_brush_type", getattr(brush, "gpencil_tool", None))



_GP_PRIMITIVE_TOOLS = ("builtin.line", "builtin.polyline", "builtin.arc", "builtin.curve", "builtin.box", "builtin.circle")



def _gp_draw_brush_tool():
    ob = bpy.context.active_object
    if not ob or ob.type != "GREASEPENCIL" or ob.mode != "PAINT_GREASE_PENCIL":
        return None
    paint = bpy.context.tool_settings.gpencil_paint
    if not paint:
        return None
    tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode)
    if not tool or not tool.use_brushes:
        return None
    brush = paint.brush
    if not brush or not brush.gpencil_settings:
        return None
    return tool, brush



def _gp_brush_stroke():
    found = _gp_draw_brush_tool()
    if found is None:
        return False
    tool, brush = found
    return tool.idname not in _GP_PRIMITIVE_TOOLS and _gp_brush_type(brush) != "FILL"


def _gp_fill_tool():
    found = _gp_draw_brush_tool()
    return found is not None and _gp_brush_type(found[1]) == "FILL"




def _mask_editing():
    sd = bpy.context.space_data
    if sd is None or getattr(sd, "mode", None) != "MASK":
        return False
    return bpy.context.area.type != "CLIP_EDITOR" or sd.clip is not None





keymaps = [
    Keymap("WINDOW"),
    Keymap("SCREEN"),
    Keymap("SCREEN_EDITING"),
    Keymap("REGION_CONTEXT_MENU", REGION_CONTEXT_MENU_ZONE),
    Keymap("VIEW2D", VIEW2D_ZONE),
    Keymap("VIEW2D_BUTTONS_LIST", VIEW2D_BUTTONS_LIST_ZONE),
    Keymap("USER_INTERFACE", USER_INTERFACE_ZONE),

    Keymap("3D_VIEW", VIEW_3D),
    Keymap("OBJECT_MODE", VIEW_3D, _no_object_or_object_mode),
    Keymap("MESH", VIEW_3D, editing("MESH")),
    Keymap("CURVE", VIEW_3D, editing("CURVE", "SURFACE")),
    Keymap("CURVES", VIEW_3D, operator_polls("curves.delete")),
    Keymap("ARMATURE", VIEW_3D, editing("ARMATURE")),
    Keymap("METABALL", VIEW_3D, editing("META")),
    Keymap("LATTICE", VIEW_3D, editing("LATTICE")),
    Keymap("FONT", VIEW_3D, editing("FONT")),
    Keymap("POINT_CLOUD", VIEW_3D, operator_polls("pointcloud.delete")),
    Keymap("POSE", VIEW_3D, operator_polls("pose.select_all")),
    Keymap("VERTEX_PAINT", VIEW_3D, paint_mesh(("VERTEX_PAINT",), "polygons")),
    Keymap("WEIGHT_PAINT", VIEW_3D, paint_mesh(("WEIGHT_PAINT",), "polygons")),
    Keymap("PAINT_VERTEX_SELECTION", VIEW_3D, paint_mesh(("WEIGHT_PAINT", "VERTEX_PAINT"), "use_paint_mask_vertex")),
    Keymap("PAINT_FACE_MASK", VIEW_3D, paint_mesh(("WEIGHT_PAINT", "VERTEX_PAINT", "TEXTURE_PAINT"), "use_paint_mask")),
    Keymap("SCULPT", VIEW_3D, in_mode("SCULPT")),
    Keymap("SCULPT_CURVES", VIEW_3D, in_mode("SCULPT_CURVES")),
    Keymap("PARTICLE", VIEW_3D, operator_polls("particle.select_all")),
    Keymap("OBJECT_NON_MODAL", VIEW_3D),
    Keymap("3D_VIEW_GENERIC", zone("VIEW_3D", regions=("WINDOW", "HEADER", "TOOL_HEADER", "UI", "TOOLS", "ASSET_SHELF"))),

    Keymap("GRAPH_EDITOR", zone("GRAPH_EDITOR")),
    Keymap("GRAPH_EDITOR_GENERIC", zone("GRAPH_EDITOR", regions=("WINDOW", "CHANNELS", "UI"))),
    Keymap("DOPESHEET", zone("DOPESHEET_EDITOR")),
    Keymap("DOPESHEET_GENERIC", zone("DOPESHEET_EDITOR", regions=("WINDOW", "CHANNELS", "UI"))),
    Keymap("NLA_EDITOR", zone("NLA_EDITOR")),
    Keymap("NLA_GENERIC", zone("NLA_EDITOR", regions=("WINDOW", "CHANNELS", "UI"))),
    Keymap("ANIMATION_CHANNELS", zone("GRAPH_EDITOR", "DOPESHEET_EDITOR", "NLA_EDITOR", regions=("CHANNELS",))),
    Keymap("NLA_TRACKS", zone("NLA_EDITOR", regions=("CHANNELS",))),

    Keymap("IMAGE", IMAGE),
    Keymap("UV_EDITOR", IMAGE, operator_polls("uv.select_all")),
    Keymap("IMAGE_PAINT", VIEW_3D_OR_IMAGE, _image_paint),
    Keymap("PAINT_CURVE", VIEW_3D_OR_IMAGE, _paint_curve),
    Keymap("IMAGE_GENERIC", zone("IMAGE_EDITOR", regions=("WINDOW", "UI", "TOOLS", "ASSET_SHELF"))),

    Keymap("OUTLINER", zone("OUTLINER")),
    Keymap("NODE_EDITOR", NODE),
    Keymap("NODE_GENERIC", zone("NODE_EDITOR", regions=("WINDOW", "UI", "TOOLS", "ASSET_SHELF"))),
    Keymap("SPREADSHEET_GENERIC", zone("SPREADSHEET", regions=("WINDOW", "UI"))),
    Keymap("VIDEO_SEQUENCE_EDITOR", zone("SEQUENCE_EDITOR", regions=("WINDOW", "PREVIEW", "UI", "TOOLS"))),
    Keymap("SEQUENCER", zone("SEQUENCE_EDITOR")),
    Keymap("SEQUENCER_PREVIEW", zone("SEQUENCE_EDITOR", regions=("PREVIEW",))),
    Keymap("SEQUENCER_CHANNELS", zone("SEQUENCE_EDITOR", regions=("CHANNELS",))),
    Keymap("FILE_BROWSER", zone("FILE_BROWSER", regions=("WINDOW", "HEADER", "UI", "EXECUTE", "TOOLS", "TOOL_PROPS"))),
    Keymap("FILE_BROWSER_MAIN", zone("FILE_BROWSER")),
    Keymap("FILE_BROWSER_BUTTONS", zone("FILE_BROWSER", regions=("UI",))),
    Keymap("INFO", zone("INFO")),
    Keymap("PROPERTY_EDITOR", zone("PROPERTIES")),
    Keymap("TEXT", zone("TEXT_EDITOR")),
    Keymap("TEXT_GENERIC", zone("TEXT_EDITOR", regions=("WINDOW", "UI"))),
    Keymap("CONSOLE", zone("CONSOLE")),
    Keymap("PREFERENCES", zone("PREFERENCES")),
    Keymap("PREFERENCES_NAV", zone("PREFERENCES", regions=("UI",))),

    Keymap("CLIP", zone("CLIP_EDITOR", regions=("WINDOW", "PREVIEW", "TOOLS", "UI"))),
    Keymap("CLIP_EDITOR", zone("CLIP_EDITOR")),
    Keymap("CLIP_GRAPH_EDITOR", zone("CLIP_EDITOR", regions=("PREVIEW",))),
    Keymap("CLIP_DOPESHEET_EDITOR", zone("CLIP_EDITOR", regions=("PREVIEW", "CHANNELS"))),
    Keymap("CLIP_TIME_SCRUB", zone("CLIP_EDITOR", regions=("PREVIEW",))),

    Keymap("GREASE_PENCIL", GREASE_PENCIL_ZONE),
    Keymap("GREASE_PENCIL_DRAW_MODE", VIEW_3D, grease_pencil_in("PAINT_GREASE_PENCIL", settings="gpencil_paint")),
    Keymap("GREASE_PENCIL_EDIT_MODE", VIEW_3D, grease_pencil_in("EDIT")),
    Keymap("GREASE_PENCIL_SCULPT_MODE", VIEW_3D, grease_pencil_in("SCULPT_GREASE_PENCIL", settings="gpencil_sculpt_paint")),
    Keymap("GREASE_PENCIL_WEIGHT_PAINT", VIEW_3D, grease_pencil_in("WEIGHT_GREASE_PENCIL", settings="gpencil_weight_paint")),
    Keymap("GREASE_PENCIL_VERTEX_PAINT", VIEW_3D, grease_pencil_in("VERTEX_GREASE_PENCIL", settings="gpencil_vertex_paint")),

    Keymap("GREASE_PENCIL_SELECTION", VIEW_3D, grease_pencil_in("EDIT", "SCULPT_GREASE_PENCIL", "VERTEX_GREASE_PENCIL")),
    Keymap("GREASE_PENCIL_BRUSH_STROKE", VIEW_3D, _gp_brush_stroke),
    Keymap("GREASE_PENCIL_FILL_TOOL", VIEW_3D, _gp_fill_tool),

    Keymap("MASK_EDITING", zone("CLIP_EDITOR", "IMAGE_EDITOR"), _mask_editing),
    Keymap("FRAMES", FRAMES_ZONE),
    Keymap("MARKERS", ANIMATION_ZONE),

    Keymap("TIME_SCRUB", ANIMATION_ZONE),
    Keymap("ANIMATION", ANIMATION_ZONE),
]

_by_key = {keymap.key: keymap for keymap in keymaps}



def poll(key: str) -> bool:
    return _by_key[key].poll()



UI_KEYMAPS = ("REGION_CONTEXT_MENU", "VIEW2D", "VIEW2D_BUTTONS_LIST", "USER_INTERFACE")




def has_own_keymaps(area_type: str, region_type: str, main_type: str) -> bool:
    return any(
        keymap.zone is not None
        and keymap.key not in UI_KEYMAPS
        and area_type in keymap.zone.get(region_type, ())
        and area_type not in keymap.zone.get(main_type, ())
        for keymap in keymaps
    )
