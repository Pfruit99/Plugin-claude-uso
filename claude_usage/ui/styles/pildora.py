"""Pildora: una capsula minima (luz + estado + reinicio) que al pasar el raton despliega los anillos."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QFontMetricsF

from ...formatting import fmt_remaining, fmt_tokens
from ...status import SPANS, pace_fraction
from ...texts import WINDOW_NAMES, pill_text
from ..draw import draw_card, draw_dot, draw_ring, draw_text
from ..theme import BAD, level_color
from .base import Layout

PILL_H, DETAIL_W, DETAIL_H, GAP = 40, 250, 138, 8


class Pildora:
    def _pill_width(self, ctx):
        text = pill_text(ctx.status)
        return round(QFontMetricsF(ctx.fonts.make(11, True)).horizontalAdvance(text)) + 52

    def layout(self, ctx):
        pw = self._pill_width(ctx)
        if not ctx.hover:
            return Layout(pw, PILL_H)
        return Layout(max(pw, DETAIL_W), PILL_H + GAP + DETAIL_H, ())

    def paint(self, p, ctx, layout):
        pal, f, st = ctx.pal, ctx.fonts, ctx.status
        color = ctx.fx.color(st.level)
        pill = QRectF(0, 0, self._pill_width(ctx), PILL_H)
        draw_card(p, pill, pal, radius=PILL_H / 2, border=BAD if st.exhausted else None, shine=False,
                  flash=(color, ctx.fx.flash))
        draw_dot(p, 22, PILL_H / 2, 5, color, ctx.fx.pulse)
        draw_text(p, 38, PILL_H / 2, pill_text(st), pal["text"], f.make(11, True))
        if ctx.hover:
            self._detail(p, ctx, QRectF(0, PILL_H + GAP, DETAIL_W, DETAIL_H))

    def _detail(self, p, ctx, rect):
        pal, f, cfg = ctx.pal, ctx.fonts, ctx.cfg
        draw_card(p, rect, pal, radius=18)
        r, w, cy = 28, 7, rect.y() + 52
        for cx, key in ((rect.x() + DETAIL_W * 0.27, "five"), (rect.x() + DETAIL_W * 0.73, "week")):
            window = ctx.window(key)
            pct = window.pct if window else None
            draw_ring(p, cx, cy, r, w, pct, level_color(pct, cfg["warn"], cfg["bad"]), pal,
                      pace_fraction(window, SPANS[key], ctx.now) if window else None)
            draw_text(p, cx, cy, "--" if pct is None else f"{round(pct)}%", pal["text"], f.make(11, True), "c")
            draw_text(p, cx, cy + r + 20, f"{WINDOW_NAMES[key]} · {fmt_remaining(window, ctx.now)}", pal["sub"],
                      f.make(9), "c")
        today, week = ctx.tokens
        draw_text(p, rect.x() + DETAIL_W / 2, rect.bottom() - 18,
                  f"Hoy {fmt_tokens(today)} · Semana {fmt_tokens(week)}", pal["muted"], f.make(9), "c")
