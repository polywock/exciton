from . import painter


def draw_random_shapes(p: painter.Painter):
    p.fill_color = (1, 1, 1, 1)
    p.font_size = 14
    p.draw_text((50, 50), "draw_text")

    p.fill_color = (0.2, 0.4, 0.8, 0.8)
    p.stroke_color = (1, 1, 1, 0.5)
    p.line_width = 2.0
    p.draw_rect((50, 80, 120, 28))

    p.fill_color = (0.8, 0.3, 0.2, 0.8)
    p.draw_circle((230, 94), 18)

    p.fill_color = (0.2, 0.7, 0.3, 0.8)
    p.draw_rounded((50, 130, 120, 28), 0.5)

    p.fill_color = (1, 0, 0, 1)
    p.stroke_color = (0, 0, 1, 1)
    p.line_width = 4.0
    p.text_color = (0, 0, 0, 1)
    p.draw_text_box(xy=(50, 175), text="Woot", rounding=0.4, base_pad=10)
