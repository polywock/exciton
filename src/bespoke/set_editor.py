import bpy
import typing as tp

EDITOR_TARGETS = {
    "VIEW_3D": {
        "label": "3D Viewport",
        "area_type": "VIEW_3D",
    },
    "IMAGE_EDITOR": {
        "label": "Image Editor",
        "area_type": "IMAGE_EDITOR",
        "ui_type": "IMAGE_EDITOR",
    },
    "UV_EDITOR": {
        "label": "UV Editor",
        "area_type": "IMAGE_EDITOR",
        "ui_type": "UV",
    },
    "GEOMETRY_NODE_EDITOR": {
        "label": "Geometry Node Editor",
        "area_type": "NODE_EDITOR",
        "tree_type": "GeometryNodeTree",
    },
    "COMPOSITOR": {
        "label": "Compositor",
        "area_type": "NODE_EDITOR",
        "tree_type": "CompositorNodeTree",
    },
    "SHADER_EDITOR": {
        "label": "Shader Editor",
        "area_type": "NODE_EDITOR",
        "tree_type": "ShaderNodeTree",
    },
    "TEXTURE_NODE_EDITOR": {
        "label": "Texture Node Editor",
        "area_type": "NODE_EDITOR",
        "tree_type": "TextureNodeTree",
    },
    "SEQUENCE_EDITOR": {
        "label": "Video Sequencer",
        "area_type": "SEQUENCE_EDITOR",
    },
    "CLIP_EDITOR": {
        "label": "Movie Clip Editor",
        "area_type": "CLIP_EDITOR",
    },
    "DOPESHEET_EDITOR": {
        "label": "Dope Sheet",
        "area_type": "DOPESHEET_EDITOR",
        "ui_type": "DOPESHEET",
    },
    "TIMELINE": {
        "label": "Timeline",
        "area_type": "DOPESHEET_EDITOR",
        "ui_type": "TIMELINE",
    },
    "GRAPH_EDITOR": {
        "label": "Graph Editor",
        "area_type": "GRAPH_EDITOR",
        "ui_type": "FCURVES",
    },
    "DRIVERS": {
        "label": "Drivers",
        "area_type": "GRAPH_EDITOR",
        "ui_type": "DRIVERS",
    },
    "NLA_EDITOR": {
        "label": "Nonlinear Animation",
        "area_type": "NLA_EDITOR",
    },
    "TEXT_EDITOR": {
        "label": "Text Editor",
        "area_type": "TEXT_EDITOR",
    },
    "CONSOLE": {
        "label": "Python Console",
        "area_type": "CONSOLE",
    },
    "INFO": {
        "label": "Info",
        "area_type": "INFO",
    },
    "OUTLINER": {
        "label": "Outliner",
        "area_type": "OUTLINER",
    },
    "PROPERTIES": {
        "label": "Properties",
        "area_type": "PROPERTIES",
    },
    "FILE_BROWSER": {
        "label": "File Browser",
        "area_type": "FILE_BROWSER",
        "ui_type": "FILES",
    },
    "ASSET_BROWSER": {
        "label": "Asset Browser",
        "area_type": "FILE_BROWSER",
        "ui_type": "ASSETS",
    },
    "SPREADSHEET": {
        "label": "Spreadsheet",
        "area_type": "SPREADSHEET",
    },
    "PREFERENCES": {
        "label": "Preferences",
        "area_type": "PREFERENCES",
    },
}


EDITOR_TARGET_ITEMS = [(key, spec["label"], "") for key, spec in EDITOR_TARGETS.items()]


class EXCITON_OT_set_editor(bpy.types.Operator):
    bl_idname = "exciton.bespoke_set_editor"
    bl_label = "Set editor"
    bl_options = {"REGISTER"}

    target: bpy.props.EnumProperty(
        name="Editor",
        items=EDITOR_TARGET_ITEMS,
        default="VIEW_3D",
    )

    def execute(self, context):
        area = context.area
        if area is None:
            self.report({"WARNING"}, "No active area")
            return {"CANCELLED"}
        spec = EDITOR_TARGETS[self.target]

        area.type = tp.cast(tp.Any, spec["area_type"])
        ui_type = spec.get("ui_type")
        if ui_type is not None:
            area.ui_type = ui_type

        tree_type = spec.get("tree_type")
        if tree_type is not None:
            space_data = tp.cast(bpy.types.SpaceNodeEditor, area.spaces.active)
            if not hasattr(space_data, "tree_type"):
                self.report({"WARNING"}, "Active space does not expose tree_type")
                return {"CANCELLED"}
            space_data.tree_type = tp.cast(tp.Any, tree_type)

        return {"FINISHED"}
