"""Pildora: una capsula minima (luz + estado + reinicio) que al pasar el raton despliega los anillos."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QFontMetricsF

from ...formatting import fmt_remaining, fmt_tokens
from ...status import pace_fraction, window_label, window_span
from ...texts import pill_text
from ..draw import draw_agent_chips, draw_card, draw_dot, draw_ring, draw_text
from ..theme import BAD, level_color
from .base import Layout

PILL_H, DETAIL_W, DETAIL_H, GAP, CHIPS_H = 40, 250, 138, 8, 22


class Pildora:
    def _pill_width(self, ctx):
        text = pill_text(ctx.status, ctx.agent_name)
        return round(QFontMetricsF(ctx.fonts.make(11, True)).horizontalAdvance(text)) + 52

    @staticmethod
    def _multi(ctx):
        return bool(ctx.overview and len(ctx.overview.entries) > 1)

    def _detail_height(self, ctx):
        return DETAIL_H + (CHIPS_H if self._multi(ctx) else 0)

    def layout(self, ctx):
        pw = self._pill_width(ctx)
        if not ctx.hover:
            return Layout(pw, PILL_H)
        return Layout(max(pw, DETAIL_W), PILL_H + GAP + self._detail_height(ctx), ())

    def paint(self, p, ctx, layout):
        pal, f, st = ctx.pal, ctx.fonts, ctx.status
        color = ctx.fx.color(st.level)
        pill = QRectF(0, 0, self._pill_width(ctx), PILL_H)
        draw_card(p, pill, pal, radius=PILL_H / 2, border=BAD if st.exhausted else None, shine=False,
                  flash=(color, ctx.fx.flash))
        draw_dot(p, 22, PILL_H / 2, 5, color, ctx.fx.pulse)
        draw_text(p, 38, PILL_H / 2, pill_text(st, ctx.agent_name), pal["text"], f.make(11, True))
        if ctx.hover:
            self._detail(p, ctx, QRectF(0, PILL_H + GAP, DETAIL_W, self._detail_height(ctx)))

    def _detail(self, p, ctx, rect):
        pal, f, cfg = ctx.pal, ctx.fonts, ctx.cfg
        draw_card(p, rect, pal, radius=18)
        r, w, cy = 28, 7, rect.y() + 52
        windows = [(key, ctx.window(key)) for key in ("five", "week") if ctx.window(key)]
        xs = (0.5,) if len(windows) == 1 else (0.27, 0.73)
        for frac, (key, window) in zip(xs, windows):
            cx, pct = rect.x() + DETAIL_W * frac, window.pct
            draw_ring(p, cx, cy, r, w, pct, level_color(pct, cfg["warn"], cfg["bad"]), pal,
                      pace_fraction(window, window_span(key, window), ctx.now))
            draw_text(p, cx, cy, f"{round(pct)}%", pal["text"], f.make(11, True), "c")
            draw_text(p, cx, cy + r + 20, f"{window_label(key, window)} · {fmt_remaining(window, ctx.now)}",
                      pal["sub"], f.make(9), "c")
        if not windows:
            draw_text(p, rect.x() + DETAIL_W / 2, cy, "Sin datos", pal["muted"], f.make(10), "c")
        y = rect.y() + DETAIL_H - 18
        if ctx.agent_name is None:  # los tokens son de Claude
            today, week = ctx.tokens
            draw_text(p, rect.x() + DETAIL_W / 2, y, f"Hoy {fmt_tokens(today)} · Semana {fmt_tokens(week)}",
                      pal["muted"], f.make(9), "c")
        if self._multi(ctx):
            draw_agent_chips(p, ctx.overview.entries, pal, f, rect.x() + 18, y + 22)
