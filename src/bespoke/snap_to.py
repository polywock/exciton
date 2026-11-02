import bpy

TARGETS = [
    ("INCREMENT", "Increment", ""),
    ("GRID", "Grid", ""),
    ("VERTEX", "Vertex", ""),
    ("EDGE", "Edge", ""),
    ("FACE", "Face", ""),
    ("VOLUME", "Volume", ""),
    ("EDGE_MIDPOINT", "Edge Center", ""),
    ("EDGE_PERPENDICULAR", "Edge Perpendicular", ""),
    ("FACE_MIDPOINT", "Face Center", ""),
    ("FACE_PROJECT", "Face Project", ""),
    ("FACE_NEAREST", "Face Nearest", ""),
]



class EXCITON_OT_bespoke_snap_to(bpy.types.Operator):
    bl_idname = "exciton.bespoke_snap_to"
    bl_label = "Snap To"
    bl_options = {"REGISTER"}

    target: bpy.props.EnumProperty(items=TARGETS, default="INCREMENT")

    def execute(self, context):
        tool_settings = context.tool_settings


        tool_settings.snap_elements = {self.target}
        tool_settings.use_snap = True
        return {"FINISHED"}
