from . import defaults as defaults
import typing as tp


def register_draw_handlers(cb: tp.Callable[[], None]) -> list[tuple[tp.Any, tp.Any, str]]:
    handles = []
    for area_type in defaults.AREA_TYPE_TO_REGIONS:
        space = defaults.AREA_TYPES_TO_SPACE[area_type]
        for region_type in defaults.AREA_TYPE_TO_REGIONS[area_type]:
            handles.append((space, space.draw_handler_add(cb, (), region_type, "POST_PIXEL"), region_type))
    return handles



def unregister_draw_handlers(handles: list[tuple[tp.Any, tp.Any, str]]):
    for space, handle, region_type in handles:
        space.draw_handler_remove(handle, region_type)
