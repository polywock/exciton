import bpy

_MESH_TYPES = {"VERTEX": "VERT", "EDGE": "EDGE", "FACE": "FACE"}




class EXCITON_OT_bespoke_uv_select_mode(bpy.types.Operator):
    bl_idname = "exciton.bespoke_uv_select_mode"
    bl_label = "UV Select Mode"

    bl_options = {"REGISTER", "UNDO"}

    type: bpy.props.EnumProperty(
        items=[("VERTEX", "Vertex", ""), ("EDGE", "Edge", ""), ("FACE", "Face", "")],
        default="VERTEX",
    )

    @classmethod
    def poll(cls, context):
        return bpy.ops.uv.select_all.poll()

    def execute(self, context):
        if context.tool_settings.use_uv_select_sync:
            return bpy.ops.mesh.select_mode(type=_MESH_TYPES[self.type])
        return bpy.ops.uv.select_mode(type=self.type)
