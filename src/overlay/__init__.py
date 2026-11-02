import typing as tp
import bpy
from time import monotonic
from . import helpers
from .. import ribbon
from .. import configs
from .. import types
from .. import utils
from .. import windows
from . import defaults
from . import engine
from . import painter
from ..ribbon.summons import confirm
from ..ribbon.summons import pointer
from ..ribbon.summons import screenshot
from .center import CenterCaption
from ..ribbon.display import ReadingSpeed

FRAME_SECONDS = 1 / 20

ATTENTION_COLOR = (1.0, 0.78, 0.1)
ATTENTION_WIDTH = 4



class Overlay:

    center = CenterCaption
    speed = ReadingSpeed

    _engine: engine.Engine | None = None

    _draw_targets: set[tuple[int, int]] = set()
    _drew = False
    _draw_handles: list[tuple[tp.Any, tp.Any, str]] = []

    _window_key: int | None = None

    _attention = 0.0

    @classmethod
    def register(cls):
        cls._draw_handles = helpers.register_draw_handlers(cls.on_draw)
        utils.register_timer(cls.on_timer, 1, True)

    @classmethod
    def unregister(cls):
        helpers.unregister_draw_handlers(cls._draw_handles)
        cls._draw_handles = []



    @classmethod
    def on_timer(cls):
        previous, cls._draw_targets = cls._draw_targets, set()
        now = monotonic()
        cls._update_attention(now)
        cls._update_pointer(now)
        ribbon.Ribbon.prune(lambda job: engine.is_showing(job, now))

        center = CenterCaption.active(now)


        snapshot = configs.get_config().get("_active_snapshot")
        if not snapshot or not (ribbon.Ribbon._jobs or center):
            cls._set_drew(False)
            return FRAME_SECONDS

        speed = ReadingSpeed.current()
        for job in ribbon.Ribbon._jobs:
            if job.state in ("sealed", "done"):
                job.display.advance(now, speed)


        window = windows.chat_window()
        if window is None:
            cls._set_drew(False)
            return FRAME_SECONDS

        if cls._window_key is not None and cls._window_key != window.as_pointer():
            utils.redraw_all()
            previous = set()
        cls._window_key = window.as_pointer()
        ui_scale = bpy.context.preferences.system.ui_scale
        cls._engine = engine.Engine(snapshot, ui_scale)
        top = engine.column_top(window, defaults.AREA_TYPE_TO_REGIONS, ui_scale)
        cls._engine.run(ribbon.Ribbon._jobs, now, top, CenterCaption.layout(window))

        covered = [(x, window.height - y - h, w, h) for x, y, w, h in (box.rect for box in cls._engine.boxes)]
        for area in window.screen.areas:
            for region in area.regions:
                target = (area.as_pointer(), region.as_pointer())
                if any(_overlaps(rect, (region.x, region.y, region.width, region.height)) for rect in covered):
                    cls._draw_targets.add(target)

                if target in cls._draw_targets or target in previous:
                    area.tag_redraw()

        cls._set_drew(bool(cls._draw_targets))
        return FRAME_SECONDS



    @classmethod
    def refresh(cls):
        cls.on_timer()


    @classmethod
    def _set_drew(cls, drew: bool):
        if cls._drew and not drew:
            utils.redraw_all()
        cls._drew = drew


    @classmethod
    def _update_attention(cls, now: float):
        alpha = confirm.attention_alpha(now)
        if alpha or cls._attention:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        cls._attention = alpha


    _pointer_areas: set[tp.Any] = set()

    @classmethod
    def _update_pointer(cls, now: float):
        p = pointer.active(now)
        areas: set[tp.Any] = set()
        if p is not None:
            try:
                left, bottom, right, top = pointer.extent(p)
                for area in p.window.screen.areas:
                    if area.x < right and left < area.x + area.width and area.y < top and bottom < area.y + area.height:
                        areas.add(area)
            except ReferenceError:
                pointer.clear()
        for area in areas | cls._pointer_areas:
            try:
                area.tag_redraw()
            except ReferenceError:
                pass
        cls._pointer_areas = areas

    @classmethod
    def on_draw(cls):

        if screenshot.capturing:
            return
        ctx = bpy.context


        alpha = confirm.attention_alpha(monotonic()) if cls._attention else 0.0
        if alpha and ctx.region.type == "WINDOW":
            width = ATTENTION_WIDTH * ctx.preferences.system.ui_scale
            painter.draw_region_frame(ctx.region.width, ctx.region.height, width, (*ATTENTION_COLOR, alpha))
        if cls._engine is not None and (ctx.area.as_pointer(), ctx.region.as_pointer()) in cls._draw_targets:
            cls._engine.draw(ctx.window.height, ctx.region)

        cls._draw_pointer(ctx)


    @classmethod
    def _draw_pointer(cls, ctx):
        now = monotonic()
        p = pointer.active(now)
        if p is None or ctx.window != p.window:
            return
        region = ctx.region
        left, bottom, right, top = pointer.extent(p)
        if region.x < right and left < region.x + region.width and region.y < top and bottom < region.y + region.height:
            pointer.draw(p, region, now)


def _overlaps(a: types.FloatRect, b: types.FloatRect) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
