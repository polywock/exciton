import gpu
import typing as tp
from gpu_extras.batch import batch_for_shader
import contextlib
import functools
import math
import blf
from .. import types

ColorTuple = types.ColorTuple
FloatPoint = types.FloatPoint
IntPoint = types.IntPoint
FloatRect = types.FloatRect


_ALIGN = {"left": 0.0, "center": 0.5, "right": 1.0}

_PI = math.pi
_TAU = 2 * math.pi
_HALF_PI = math.pi / 2


class Painter:
    _shader: gpu.types.GPUShader | None = None

    def __init__(self, area_height: int, offset: FloatPoint):
        self.area_height = area_height
        self.offset = offset
        self.fill_color: ColorTuple = (1, 1, 1, 1)
        self.stroke_color: ColorTuple = (1, 1, 1, 1)
        self.text_color: ColorTuple = (1, 1, 1, 1)
        self.line_width: float = 0.0
        self.font_size: float = 14.0

    @classmethod
    def _get_shader(cls):
        if not cls._shader:
            cls._shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        return cls._shader


    @staticmethod
    @functools.lru_cache(maxsize=2048)
    def _get_text_dimensions(size: float, text: str) -> tuple[float, float]:
        blf.size(0, size)
        return blf.dimensions(0, text)


    def _window_rect_to_region_rect(self, rect: FloatRect) -> tuple[int, int, int, int]:
        x, y, w, h = rect
        return (
            round(x - self.offset[0]),
            round(self.area_height - y - h - self.offset[1]),
            round(w),
            round(h),
        )

    @staticmethod
    def _intersect_rects(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2 - x1, y2 - y1


    @contextlib.contextmanager
    def draw_with_clip(self, clip: FloatRect) -> tp.Iterator[bool]:
        region_clip = self._window_rect_to_region_rect(clip)
        old_scissor = gpu.state.scissor_get()
        scissor = self._intersect_rects(region_clip, old_scissor)
        visible = scissor is not None

        if not visible:


            x, y, w, h = old_scissor
            scissor = (x, y, 1 if w > 0 else 0, 1 if h > 0 else 0)

        gpu.state.scissor_set(*scissor)
        try:
            yield visible
        finally:
            gpu.state.scissor_set(*old_scissor)



    def draw_clipped(
        self,
        clip: FloatRect,
        draw_fn: tp.Callable[[], tp.Any],
    ) -> tp.Any:
        with self.draw_with_clip(clip) as visible:
            if not visible:
                return None
            return draw_fn()


    @staticmethod
    def _build_outline_geometry(outer, inner):
        n = len(outer)
        vertices = [v for pair in zip(outer, inner) for v in pair]
        indices = [
            tri
            for i in range(n)
            for tri in (
                (i * 2, i * 2 + 1, ((i + 1) % n) * 2),
                (i * 2 + 1, ((i + 1) % n) * 2 + 1, ((i + 1) % n) * 2),
            )
        ]
        return vertices, indices


    @staticmethod
    def _build_fan_geometry(center, perimeter):
        n = len(perimeter)
        vertices = [center] + list(perimeter)
        indices = [(0, i, (i % n) + 1) for i in range(1, n + 1)]
        return vertices, indices


    @staticmethod
    def _draw_batches(batch_fill, color, batch_outline=None, line_color=(1, 1, 1, 1)):
        shader = Painter._get_shader()
        shader.bind()
        og_state = gpu.state.blend_get()
        gpu.state.blend_set("ALPHA")

        shader.uniform_float("color", color)
        batch_fill.draw(shader)

        if batch_outline:
            shader.uniform_float("color", line_color)
            batch_outline.draw(shader)

        gpu.state.blend_set(og_state)


    @staticmethod
    def _circle_perimeter(xy: FloatPoint, radius, segments):
        return [
            (
                xy[0] + math.cos(i / segments * _TAU) * radius,
                xy[1] + math.sin(i / segments * _TAU) * radius,
            )
            for i in range(segments)
        ]


    @staticmethod
    def _rounded_rect_perimeter(xy: FloatPoint, w, h, r, segments):
        r = max(0, min(r, w / 2, h / 2))
        corners = [
            (xy[0] + w - r, xy[1] + h - r, 0),
            (xy[0] + r, xy[1] + h - r, _HALF_PI),
            (xy[0] + r, xy[1] + r, _PI),
            (xy[0] + w - r, xy[1] + r, 3 * _HALF_PI),
        ]
        return [
            (
                cx + math.cos(start + i / segments * _HALF_PI) * r,
                cy + math.sin(start + i / segments * _HALF_PI) * r,
            )
            for cx, cy, start in corners
            for i in range(segments + 1)
        ]

    def draw_text_box(
        self,
        xy: FloatPoint,
        text: str,
        rounding: float = 0,
        *,
        base_pad: float | None = None,
        more_pads: ColorTuple | None = None,
        min_width: float | None = None,
        align: str = "left",
    ):
        dims = Painter._get_text_dimensions(self.font_size, text)

        base_pad = base_pad or 0.0
        pads = [v + base_pad for v in (more_pads or (0, 0, 0, 0))]


        pads[2] += self.font_size * 0.32

        rect_width = max(dims[0] + pads[1] + pads[3], min_width or -math.inf)
        rect_height = self.font_size + pads[0] + pads[2]

        rect = (xy[0], xy[1], rect_width, rect_height)
        if rounding > 0:
            self.draw_rounded(rect, rounding)
        else:
            self.draw_rect(rect)
        spare = rect_width - pads[1] - pads[3] - dims[0]
        self.draw_text((xy[0] + pads[3] + spare * _ALIGN[align], xy[1] + pads[0]), text)

        return rect_width, rect_height

    def draw_multiline_text_box(
        self,
        xy: FloatPoint,
        lines: tp.Sequence[str],
        line_spacing: float = 1.4,
        rounding: float = 0,
        *,
        base_pad: float | None = None,
        more_pads: ColorTuple | None = None,
        min_width: float | None = None,
        align: str = "left",
    ) -> tuple[float, float]:
        if not lines:
            return (0.0, 0.0)
        pads, line_h, rect_width, rect_height = self._multiline_box(lines, line_spacing, base_pad, more_pads, min_width)

        rect = (xy[0], xy[1], rect_width, rect_height)
        if rounding > 0:
            self.draw_rounded(rect, rounding)
        else:
            self.draw_rect(rect)

        inner = rect_width - pads[1] - pads[3]
        for i, line in enumerate(lines):
            spare = inner - Painter._get_text_dimensions(self.font_size, line)[0]
            self.draw_text((xy[0] + pads[3] + spare * _ALIGN[align], xy[1] + pads[0] + i * line_h), line)

        return rect_width, rect_height


    def measure_multiline_text_box(
        self,
        lines: tp.Sequence[str],
        line_spacing: float = 1.4,
        *,
        base_pad: float | None = None,
        more_pads: ColorTuple | None = None,
        min_width: float | None = None,
    ) -> tuple[float, float]:
        if not lines:
            return (0.0, 0.0)
        _, _, rect_width, rect_height = self._multiline_box(lines, line_spacing, base_pad, more_pads, min_width)
        return rect_width, rect_height


    def _multiline_box(
        self,
        lines: tp.Sequence[str],
        line_spacing: float,
        base_pad: float | None,
        more_pads: ColorTuple | None,
        min_width: float | None,
    ) -> tuple[list[float], float, float, float]:
        base_pad = base_pad or 0.0
        pads = [v + base_pad for v in (more_pads or (0, 0, 0, 0))]
        pads[2] += self.font_size * 0.32

        line_h = self.font_size * line_spacing
        total_text_h = self.font_size + line_h * (len(lines) - 1)
        max_text_w = max(Painter._get_text_dimensions(self.font_size, ln)[0] for ln in lines)

        rect_width = max(max_text_w + pads[1] + pads[3], min_width or -math.inf)
        rect_height = total_text_h + pads[0] + pads[2]
        return pads, line_h, rect_width, rect_height

    def draw_text(self, xy: FloatPoint, text: str):
        c = self.text_color
        x = xy[0] - self.offset[0]
        y = self.area_height - xy[1] - self.font_size - self.offset[1]
        blf.position(0, x, y, 0)
        blf.size(0, self.font_size)
        blf.color(0, c[0], c[1], c[2], c[3])
        blf.draw(0, text)
        blf.draw(0, text)


    def draw_rect(self, b: FloatRect):
        x, y, w, h = b
        x -= self.offset[0]
        y = self.area_height - y - h - self.offset[1]
        outer = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

        batch_fill = batch_for_shader(
            Painter._get_shader(),
            "TRIS",
            {"pos": outer},
            indices=[(0, 1, 2), (2, 3, 0)],
        )

        batch_outline = None
        if self.line_width > 0:
            iw, ih = w - 2 * self.line_width, h - 2 * self.line_width
            if iw > 0 and ih > 0:
                ix, iy = x + self.line_width, y + self.line_width
                inner = [(ix, iy), (ix + iw, iy), (ix + iw, iy + ih), (ix, iy + ih)]
                verts, indices = Painter._build_outline_geometry(outer, inner)
                batch_outline = batch_for_shader(
                    Painter._get_shader(),
                    "TRIS",
                    {"pos": verts},
                    indices=indices,
                )

        Painter._draw_batches(batch_fill, self.fill_color, batch_outline, self.stroke_color)


    def draw_circle(self, xy: FloatPoint, radius: float, segments: int = 32):
        cx = xy[0] - self.offset[0]
        cy = self.area_height - xy[1] - self.offset[1]
        outer = Painter._circle_perimeter((cx, cy), radius, segments)
        verts, indices = Painter._build_fan_geometry((cx, cy), outer)

        batch_fill = batch_for_shader(Painter._get_shader(), "TRIS", {"pos": verts}, indices=indices)

        batch_outline = None
        if self.line_width > 0 and radius > self.line_width:
            inner = Painter._circle_perimeter((cx, cy), radius - self.line_width, segments)
            verts, indices = Painter._build_outline_geometry(outer, inner)
            batch_outline = batch_for_shader(Painter._get_shader(), "TRIS", {"pos": verts}, indices=indices)

        Painter._draw_batches(batch_fill, self.fill_color, batch_outline, self.stroke_color)


    def draw_rounded(self, b: FloatRect, r: float, segments: int = 8):
        x, y, w, h = b
        x -= self.offset[0]
        y = self.area_height - y - h - self.offset[1]
        r = max(0.0, min(r, 1.0)) * min(w / 2, h / 2)
        outer = Painter._rounded_rect_perimeter((x, y), w, h, r, segments)
        verts, indices = Painter._build_fan_geometry((x + w / 2, y + h / 2), outer)

        batch_fill = batch_for_shader(Painter._get_shader(), "TRIS", {"pos": verts}, indices=indices)

        batch_outline = None
        if self.line_width > 0:
            iw, ih = w - 2 * self.line_width, h - 2 * self.line_width
            if iw > 0 and ih > 0:
                inner = Painter._rounded_rect_perimeter(
                    (x + self.line_width, y + self.line_width), iw, ih, r - self.line_width, segments
                )
                verts, indices = Painter._build_outline_geometry(outer, inner)
                batch_outline = batch_for_shader(
                    Painter._get_shader(),
                    "TRIS",
                    {"pos": verts},
                    indices=indices,
                )

        Painter._draw_batches(batch_fill, self.fill_color, batch_outline, self.stroke_color)



def draw_region_frame(region_width: int, region_height: int, width: float, color: ColorTuple):
    w, h = region_width, region_height
    t = min(width, w / 2, h / 2)
    rects = [(0, 0, w, t), (0, h - t, w, t), (0, t, t, h - 2 * t), (w - t, t, t, h - 2 * t)]
    pos = []
    indices = []
    for x, y, rw, rh in rects:
        i = len(pos)
        pos += [(x, y), (x + rw, y), (x + rw, y + rh), (x, y + rh)]
        indices += [(i, i + 1, i + 2), (i, i + 2, i + 3)]
    shader = Painter._get_shader()
    batch = batch_for_shader(shader, "TRIS", {"pos": pos}, indices=indices)
    gpu.state.blend_set("ALPHA")
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set("NONE")
