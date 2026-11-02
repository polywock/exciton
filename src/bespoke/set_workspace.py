import bpy


class EXCITON_OT_bespoke_set_workspace(bpy.types.Operator):
    bl_idname = "exciton.bespoke_set_workspace"
    bl_label = "Set workspace with name"
    bl_options = {"REGISTER"}

    name: bpy.props.StringProperty()

    def execute(self, context):
        if not self.name:
            self.report({"WARNING"}, "No workspace specified")
            return {"CANCELLED"}

        found_ws: bpy.types.WorkSpace | None = None

        for ws in bpy.data.workspaces:
            if ws.name.lower() == self.name.lower():
                found_ws = ws
                break

        if not found_ws:
            self.report({"WARNING"}, f"No workspace named {self.name}")
            return {"CANCELLED"}

        if context.window:
            context.window.workspace = found_ws
            return {"FINISHED"}
        return {"CANCELLED"}
