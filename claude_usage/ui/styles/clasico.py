"""Clasico: el diseno anterior (anillos o barras, tamano compacto o completo) con tokens y contexto."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPen

from ... import formatting
from ...status import SPANS, pace_fraction
from ..draw import draw_card, draw_ring, draw_text, draw_track
from ..theme import BAD, PAD, WARN, level_color
from .base import Layout, gear_zone

WIDTHS = {"compact": 290, "full": 330}


def exhausted_windows(real):
    return [w for w in (real.five, real.week) if w and w.pct >= 100]


class Clasico:
    def layout(self, ctx):
        full, ring = ctx.cfg["size"] == "full", ctx.cfg["view"] == "ring"
        no_data = ctx.real.five is None and ctx.real.week is None
        h = 44 + (38 if exhausted_windows(ctx.real) else 0) + (20 if no_data else 0)
        h += (150 if full else 114) if ring else (134 if full else 90)
        h += (60 if full else 0) + 8
        w = WIDTHS[ctx.cfg["size"]]
        zones = ((QRectF(PAD + 104, 0, 40, 40), "options"), (QRectF(w - 150, 0, 150, 40), "refresh")) if full \
            else (gear_zone(w),)
        return Layout(w, h, zones)

    def paint(self, p, ctx, layout):
        pal, f, cfg = ctx.pal, ctx.fonts, ctx.cfg
        W, H = layout.w, layout.h
        five, week = ctx.limits.five, ctx.limits.week
        updated, context = ctx.limits.updated, ctx.limits.context
        full, ring = cfg["size"] == "full", cfg["view"] == "ring"
        exhausted = exhausted_windows(ctx.real)
        draw_card(p, QRectF(0, 0, W, H), pal, border=BAD if exhausted else None)

        draw_text(p, PAD, 24, "Uso de Claude" if full else "Claude", pal["text"], f.make(12 if full else 11, True))
        icon_font = f.make(11, icon=True)
        if full:
            ago = formatting.fmt_ago(updated, ctx.now)
            color = WARN if ctx.stale or not updated else pal["muted"]
            draw_text(p, W - PAD, 24, ago, color, f.make(9), "e")
            width = QFontMetricsF(f.make(9)).horizontalAdvance(ago)
            draw_text(p, W - PAD - width - 12, 24, f.glyph["refresh"], color, f.make(9, icon=True), "c")
            if ctx.hover:
                draw_text(p, PAD + 124, 24, f.glyph["settings"], pal["muted"], icon_font, "c")
        else:
            draw_text(p, W - PAD - 6, 24, f.glyph["settings"], pal["muted"], icon_font, "c")

        y = 44
        if exhausted:
            real = ctx.real
            both = len(exhausted) == 2
            msg = ("Límites de 5 h y semanal agotados" if both
                   else "Límite de 5 h agotado" if real.five and real.five.pct >= 100 else "Límite semanal agotado")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["banner_bg"]))
            p.drawRoundedRect(QRectF(PAD, y, W - 2 * PAD, 28), 9, 9)
            draw_text(p, PAD + 10, y + 14, f.glyph["warning"], pal["banner_text"], f.make(10, icon=True), "w")
            draw_text(p, PAD + 30, y + 14, msg, pal["banner_text"], f.make(9))
            y += 38
        if five is None and week is None:
            draw_text(p, PAD, y + 4, "Sin datos de límites: activa la línea de estado", WARN, f.make(8))
            y += 20

        y = self._rings(p, ctx, W, y, five, week, full) if ring else self._bars(p, ctx, W, y, five, week, full)

        if full:
            p.setPen(QPen(QColor(pal["border"]), 1))
            p.drawLine(QPointF(PAD, y + 4), QPointF(W - PAD, y + 4))
            today, wk = ctx.tokens
            stats = (("Hoy", formatting.fmt_tokens(today)), ("Semana", formatting.fmt_tokens(wk)),
                     ("Contexto", "--" if context is None else f"{round(context)}%"))
            inner = W - 2 * PAD
            for i, (label, value) in enumerate(stats):
                x = PAD + inner * (2 * i + 1) / 6
                draw_text(p, x, y + 22, label, pal["muted"], f.make(9), "c")
                draw_text(p, x, y + 42, value, pal["text"], f.make(13, True), "c")

    # anillos
    def _rings(self, p, ctx, W, y, five, week, full):
        r, w = (44, 10) if full else (32, 8)
        cy = y + (78 if full else 58)
        for cx, label, window, key in ((W * 0.25, "5 h", five, "five"), (W * 0.75, "Semana", week, "week")):
            self._ring(p, ctx, cx, cy, r, w, label, window, key, full)
        return cy + r + (28 if full else 24)

    def _ring(self, p, ctx, cx, cy, r, w, label, window, key, full):
        pal, f = ctx.pal, ctx.fonts
        pct = window.pct if window else None
        done = pct is not None and pct >= 100
        color = level_color(pct, ctx.cfg["warn"], ctx.cfg["bad"])
        draw_text(p, cx, cy - r - w / 2 - 10, label, pal["sub"], f.make(10 if full else 9), "c")
        draw_ring(p, cx, cy, r, w, pct, color, pal, pace_fraction(window, SPANS[key], ctx.now) if window else None)
        draw_text(p, cx, cy, "--" if pct is None else f"{round(pct)}%", BAD if done else pal["text"],
                  f.make(17 if full else 13, True), "c")
        rem = formatting.fmt_remaining(window, ctx.now)
        draw_text(p, cx, cy + r + w / 2 + 14, f"vuelve en {rem}" if done else rem,
                  BAD if done else pal["sub"], f.make(9), "c")

    # barras
    def _bars(self, p, ctx, W, y, five, week, full):
        if full:
            self._bar(p, ctx, W, y + 12, "Ventana de 5 horas", five, "five", True)
            self._bar(p, ctx, W, y + 82, "Semanal", week, "week", True)
            return y + 134
        self._bar(p, ctx, W, y + 16, "5 horas", five, "five", False)
        self._bar(p, ctx, W, y + 62, "Semana", week, "week", False)
        return y + 90

    def _bar(self, p, ctx, W, y, label, window, key, full):
        pal, f, cfg = ctx.pal, ctx.fonts, ctx.cfg
        w = W - 2 * PAD
        pct = window.pct if window else None
        done = pct is not None and pct >= 100
        rem = formatting.fmt_remaining(window, ctx.now)
        pace = pace_fraction(window, SPANS[key], ctx.now) if window else None
        color = level_color(pct, cfg["warn"], cfg["bad"])
        if full:
            draw_text(p, PAD, y, label, pal["text"], f.make(11))
            draw_text(p, PAD + w, y, "--" if pct is None else f"{round(pct)}%", BAD if done else pal["sub"],
                      f.make(11, True), "e")
            draw_track(p, PAD, y + 14, w, 8, pct, color, pal, pace)
            draw_text(p, PAD, y + 38, f"Vuelve en {rem}" if done else f"Se reinicia en {rem}",
                      BAD if done else pal["muted"], f.make(9))
        else:
            right = "--" if pct is None else (f"100% · vuelve en {rem}" if done else f"{round(pct)}% · {rem}")
            draw_text(p, PAD, y, label, pal["text"], f.make(10))
            draw_text(p, PAD + w, y, right, BAD if done else pal["sub"], f.make(9), "e")
            draw_track(p, PAD, y + 12, w, 6, pct, color, pal, pace)
