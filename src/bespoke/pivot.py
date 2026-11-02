import bpy


class EXCITON_OT_bespoke_pivot(bpy.types.Operator):
    bl_idname = "exciton.bespoke_pivot"
    bl_label = "Set pivot point"
    bl_options = {"REGISTER"}

    type: bpy.props.EnumProperty(
        items=[
            ("BOUNDING_BOX_CENTER", "Bounding Box Center", ""),
            ("CURSOR", "Cursor", ""),
            ("INDIVIDUAL_ORIGINS", "Individual Origins", ""),
            ("MEDIAN_POINT", "Median Point", ""),
            ("ACTIVE_ELEMENT", "Active Element", ""),
        ],
        default="BOUNDING_BOX_CENTER",
    )

    def execute(self, context):
        tool_settings = context.tool_settings
        tool_settings.transform_pivot_point = self.type
        return {"FINISHED"}
