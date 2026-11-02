import bpy


class EXCITON_OT_bespoke_toggle_state(bpy.types.Operator):
    bl_idname = "exciton.bespoke_toggle"
    bl_label = "Toggle State"
    bl_options = {"REGISTER"}

    type: bpy.props.EnumProperty(
        items=[
            ("AFFECT_ORIGINS", "Affect Only Origins", ""),
            ("AFFECT_LOCATIONS", "Affect Only Locations", ""),
            ("AFFECT_PARENTS", "Affect Only Parents", ""),
        ],
        default="AFFECT_ORIGINS",
    )

    mode: bpy.props.EnumProperty(
        items=[
            ("TOGGLE", "Toggle", ""),
            ("ON", "Turn on", ""),
            ("OFF", "Turn off", ""),
        ],
        default="TOGGLE",
    )

    def execute(self, context):
        if self.type == "AFFECT_ORIGINS":
            context.tool_settings.use_transform_data_origin = self.transform(context.tool_settings.use_transform_data_origin)
            return {"FINISHED"}
        elif self.type == "AFFECT_LOCATIONS":
            context.tool_settings.use_transform_pivot_point_align = self.transform(
                context.tool_settings.use_transform_pivot_point_align
            )
            return {"FINISHED"}
        elif self.type == "AFFECT_PARENTS":
            context.tool_settings.use_transform_skip_children = self.transform(context.tool_settings.use_transform_skip_children)
            return {"FINISHED"}

        return {"CANCELLED"}

    def transform(self, value: bool, inverse=False):
        if self.mode == "ON":
            value = False if inverse else True
        elif self.mode == "OFF":
            value = True if inverse else False
        elif self.mode == "TOGGLE":
            value = not value
        return value
