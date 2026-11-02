import bpy

TARGETS = [
    ("OBJECT", "Object Mode", ""),
    ("EDIT", "Edit Mode", ""),
    ("POSE", "Pose Mode", ""),
    ("SCULPT", "Sculpt Mode", ""),
    ("VERTEX_PAINT", "Vertex Paint", ""),
    ("WEIGHT_PAINT", "Weight Paint", ""),
    ("TEXTURE_PAINT", "Texture Paint", ""),
    ("PARTICLE_EDIT", "Particle Edit", ""),
    ("DRAW", "Draw Mode", ""),
]
_LABELS = {target: label for target, label, _ in TARGETS}



_MODE_BY_TYPE = {
    "CURVES": {"SCULPT": "SCULPT_CURVES"},
    "GREASEPENCIL": {
        "SCULPT": "SCULPT_GREASE_PENCIL",
        "VERTEX_PAINT": "VERTEX_GREASE_PENCIL",
        "WEIGHT_PAINT": "WEIGHT_GREASE_PENCIL",
        "DRAW": "PAINT_GREASE_PENCIL",
    },
}


class EXCITON_OT_bespoke_set_mode(bpy.types.Operator):
    bl_idname = "exciton.bespoke_set_mode"
    bl_label = "Set Mode"

    bl_options = {"REGISTER", "UNDO"}

    target: bpy.props.EnumProperty(items=TARGETS, default="OBJECT")

    @classmethod
    def poll(cls, context):
        return bpy.ops.object.mode_set.poll()

    def execute(self, context):
        ob = context.active_object
        mode = _MODE_BY_TYPE.get(ob.type, {}).get(self.target, self.target)


        try:
            entered = mode != "DRAW" and "PASS_THROUGH" not in bpy.ops.object.mode_set(mode=mode)
        except TypeError:
            entered = False
        if not entered:
            type_name = ob.bl_rna.properties["type"].enum_items[ob.type].name
            self.report({"WARNING"}, f"{_LABELS[self.target]} isn't available for {type_name} objects")
            return {"CANCELLED"}
        return {"FINISHED"}
