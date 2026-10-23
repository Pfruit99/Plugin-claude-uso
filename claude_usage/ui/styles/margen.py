"""Margen: el uso traducido a tiempo util ('Te sobra 1 h 02 min de margen') sobre una sola barra."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QFontMetricsF

from ...status import pace_fraction, window_span
from ...texts import margin_parts, other_window_note
from ..draw import draw_agent_chips, draw_card, draw_text, draw_track
from ..theme import BAD, NO_DATA, PAD
from .base import Layout, gear_zone

W, H = 290, 172


class Margen:
    def layout(self, ctx):
        return Layout(W, H, (gear_zone(W),))

    def paint(self, p, ctx, layout):
        pal, f, st, ov = ctx.pal, ctx.fonts, ctx.status, ctx.overview
        color = ctx.fx.color(st.level)
        draw_card(p, QRectF(0, 0, W, H), pal, border=BAD if st.exhausted else None, flash=(color, ctx.fx.flash))
        agent = ov.chosen_label if ov and ov.chosen else "Claude"
        draw_text(p, PAD, 24, f"{agent} · {st.label}" if st.key else agent, pal["muted"], f.make(10))
        draw_text(p, W - PAD - 6, 24, f.glyph["settings"], pal["muted"], f.make(11, icon=True), "c")

        before, value, after = margin_parts(st)
        draw_text(p, PAD, 50, before, pal["sub"], f.make(10))
        draw_text(p, PAD, 78, value, color, f.make(24, True))
        if after:
            x = PAD + QFontMetricsF(f.make(24, True)).horizontalAdvance(value) + 8
            draw_text(p, x, 82, after, pal["sub"], f.make(10))

        window = ctx.window(st.key)
        pace = pace_fraction(window, window_span(st.key, window), ctx.now) if window else None
        track_w = W - 2 * PAD
        if pace is not None and 0.02 < pace < 0.98:  # etiqueta "ahora" sobre la marca de ritmo
            draw_text(p, PAD + track_w * pace, 104, "ahora", pal["muted"], f.make(8), "c")
        draw_track(p, PAD, 114, track_w, 8, window.pct if window else None, color if window else NO_DATA, pal,
                   pace, ghost=True)
        if ov and len(ov.entries) > 1:
            draw_agent_chips(p, ov.entries, pal, f, PAD, 146)
        else:
            draw_text(p, PAD, 146, other_window_note(st, ctx.limits), pal["muted"], f.make(9))
