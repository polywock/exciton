from .. import utils
from . import set_editor
from . import pivot
from . import toggle_state
from . import set_workspace
from . import set_mode
from . import play_animation
from . import uv_select_mode
from . import snap_to
from . import add_modifier

classes = [
    set_editor.EXCITON_OT_set_editor,
    set_workspace.EXCITON_OT_bespoke_set_workspace,
    set_mode.EXCITON_OT_bespoke_set_mode,
    play_animation.EXCITON_OT_bespoke_play_animation,
    uv_select_mode.EXCITON_OT_bespoke_uv_select_mode,
    pivot.EXCITON_OT_bespoke_pivot,
    toggle_state.EXCITON_OT_bespoke_toggle_state,
    snap_to.EXCITON_OT_bespoke_snap_to,
    add_modifier.EXCITON_OT_bespoke_add_modifier,
]


def register():
    utils.register(classes)


def unregister():
    utils.unregister(classes)
