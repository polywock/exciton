





import typing as tp
import bpy

_shortcut_window: tp.Any = None



def remember(window: tp.Any):
    global _shortcut_window
    _shortcut_window = window


def all_windows() -> list[tp.Any]:
    return list(bpy.context.window_manager.windows)





def is_open(window: tp.Any) -> bool:
    if window is None:
        return False
    try:
        key = window.as_pointer()
    except ReferenceError:
        return False
    return any(w.as_pointer() == key for w in all_windows())



def chat_window() -> tp.Any:
    if is_open(_shortcut_window):
        return _shortcut_window
    return next(iter(all_windows()), None)
