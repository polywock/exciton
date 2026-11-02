import bpy




class EXCITON_OT_bespoke_play_animation(bpy.types.Operator):
    bl_idname = "exciton.bespoke_play_animation"
    bl_label = "Play Animation"
    bl_options = {"REGISTER"}

    reverse: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return bpy.ops.screen.animation_play.poll()

    def execute(self, context):
        if context.screen.is_animation_playing:
            return {"FINISHED"}
        return bpy.ops.screen.animation_play(reverse=self.reverse)
