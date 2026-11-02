import bpy

from .. import utils

_TYPES = [(item.identifier, item.name, "") for item in bpy.types.Modifier.bl_rna.properties["type"].enum_items]


_TABS = {
    "PARTICLE_SYSTEM": "PARTICLES",
    "CLOTH": "PHYSICS",
    "SOFT_BODY": "PHYSICS",
    "COLLISION": "PHYSICS",
    "DYNAMIC_PAINT": "PHYSICS",
    "FLUID": "PHYSICS",
}


_MAX_PAGES = 100




class EXCITON_OT_bespoke_add_modifier(bpy.types.Operator):
    bl_idname = "exciton.bespoke_add_modifier"
    bl_label = "Add Modifier"

    bl_options = {"REGISTER", "UNDO"}

    type: bpy.props.EnumProperty(items=_TYPES, default="SUBSURF")

    @classmethod
    def poll(cls, context):
        return bpy.ops.object.modifier_add.poll()

    def execute(self, context):

        result = bpy.ops.object.modifier_add(type=self.type, use_selected_objects=True)
        if "FINISHED" not in result:
            return result
        ob = context.object
        tab = _TABS.get(self.type, "MODIFIER")
        area = _properties_area(context, ob, tab)
        if area is None:
            return {"FINISHED"}
        space = area.spaces.active
        if space.context != tab:
            try:
                space.context = tab
            except TypeError:

                return {"FINISHED"}


        if tab == "MODIFIER" and ob.modifiers[-1] == ob.modifiers.active:
            window = context.window
            area_pointer = area.as_pointer()

            utils.set_timeout(lambda: _scroll_to_end(window, area_pointer))
        return {"FINISHED"}


def _properties_area(context, ob, tab: str):
    areas = []
    for area in context.window.screen.areas:
        if area.type != "PROPERTIES":
            continue
        space = area.spaces.active
        if space.use_pin_id and space.pin_id is not None and space.pin_id != ob:
            continue
        areas.append(area)
    if not areas:
        return None
    showing = [area for area in areas if area.spaces.active.context == tab]
    return max(showing or areas, key=lambda area: area.width * area.height)


def _scroll_to_end(window, area_pointer: int):

    if window.screen is None:
        return
    area = next((a for a in window.screen.areas if a.as_pointer() == area_pointer), None)
    region = area and next((r for r in area.regions if r.type == "WINDOW"), None)
    if region is None:
        return

    with bpy.context.temp_override(window=window, area=area, region=region):
        for _ in range(_MAX_PAGES):
            before = region.view2d.region_to_view(0, 0)
            bpy.ops.view2d.scroll_down(page=True)
            if region.view2d.region_to_view(0, 0) == before:
                break
