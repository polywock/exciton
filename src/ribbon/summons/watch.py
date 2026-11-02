



import typing as tp
import bpy
from ... import utils
from ... import windows


Hook: tp.TypeAlias = tp.Callable[[tp.Any, tp.Any], None]

_hooks: dict[str, Hook] = {}

_watched: set[int] = set()

cursor: tuple[tp.Any, float, float] | None = None


def add(name: str, hook: Hook):
    _hooks[name] = hook


def remove(name: str):
    _hooks.pop(name, None)



def ensure(window: tp.Any) -> bool:
    if not windows.is_open(window):
        return False

    _watched.intersection_update(w.as_pointer() for w in windows.all_windows())
    key = window.as_pointer()
    if key in _watched:
        return True
    area = max(window.screen.areas, key=lambda a: a.width * a.height, default=None)
    region = next((r for r in area.regions if r.type == "WINDOW"), None) if area else None
    try:
        with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
            bpy.ops.exciton.watch("INVOKE_DEFAULT")
    except Exception:
        utils.logger.info("Couldn't watch the cursor", exc_info=True)
        return False
    return key in _watched


def _see(context, event):
    global cursor
    cursor = (context.window, event.mouse_x, event.mouse_y)


class EXCITON_OT_watch(bpy.types.Operator):
    bl_idname = "exciton.watch"
    bl_label = "Exciton watch"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        self.window_key = context.window.as_pointer()
        _see(context, event)
        _watched.add(self.window_key)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        _see(context, event)
        for hook in list(_hooks.values()):
            try:
                hook(context.window, event)
            except Exception:
                utils.logger.warning("Watch hook failed", exc_info=True)
        if not _hooks:
            _watched.discard(self.window_key)
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        _watched.discard(getattr(self, "window_key", 0))


classes = (EXCITON_OT_watch,)


def register():
    utils.register(classes)


def unregister():
    _hooks.clear()
    _watched.clear()
    utils.unregister(classes)
