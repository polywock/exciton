import bpy

from .. import configs
from .. import utils
from . import tiny
from . import draw


class Panel(bpy.types.Panel):
    bl_label = "Exciton Voice Control"
    bl_idname = "EXCITON_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Voice Control"

    def draw(self, context):
        layout = self.layout
        data = configs.get_config()

        draw.testing_utils(layout, data)
        draw.debugging(layout, data)
        draw.version(layout)

        if not data.get("_init_complete"):
            draw.loading(layout)
            return

        if not utils.allows_internet():
            draw.warning(layout, "Enable Internet Access", "Edit > Preferences > System > Network > Allow Online Access.")
            return

        if data.get("token"):
            draw.logged_in(layout, data)
        else:
            draw.button(layout, "SIGN_IN", "Sign in")
            return


classes = (Panel,)


def register():
    utils.register(classes)
    tiny.register()


def unregister():
    tiny.unregister()
    utils.unregister(classes)
