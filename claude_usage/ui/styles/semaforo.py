"""Semaforo: luz de color + palabra grande + barra con marca de ritmo + reinicio."""
from PySide6.QtCore import QRectF

from ...formatting import fmt_duration, fmt_tokens
from ...status import pace_fraction, SPANS
from ...texts import WINDOW_NAMES, WORDS, hint, other_window_note
from ..draw import draw_card, draw_dot, draw_text, draw_track, qc
from ..theme import BAD, NO_DATA, PAD, STATUS_COLOR
from .base import Layout, gear_zone

W, H = 290, 184


class Semaforo:
    def layout(self, ctx):
        return Layout(W, H, (gear_zone(W),))

    def paint(self, p, ctx, layout):
        pal, f, st = ctx.pal, ctx.fonts, ctx.status
        fx = ctx.fx
        color = fx.color(st.level)
        draw_card(p, QRectF(0, 0, W, H), pal, border=BAD if st.exhausted else None, flash=(color, fx.flash))
        draw_text(p, PAD, 24, "Claude", pal["muted"], f.make(10))
        draw_text(p, W - PAD - 6, 24, f.glyph["settings"], pal["muted"], f.make(11, icon=True), "c")

        draw_dot(p, PAD + 9, 68, 8, color, fx.pulse)
        rise = 10 * (1 - fx.blend)  # fundido con deslizamiento: la palabra vieja sube y se apaga, la nueva entra desde abajo
        if fx.prev_level:
            draw_text(p, PAD + 30, 68 - 10 * fx.blend, WORDS[fx.prev_level],
                      qc(STATUS_COLOR[fx.prev_level], int(255 * (1 - fx.blend))), f.make(24, True))
        draw_text(p, PAD + 30, 68 + rise, WORDS[st.level], qc(color, int(255 * fx.blend)), f.make(24, True))
        draw_text(p, PAD, 100, hint(st), pal["sub"], f.make(10))

        window = ctx.window(st.key)
        pct = window.pct if window else None
        pace = pace_fraction(window, SPANS[st.key], ctx.now) if window else None
        draw_track(p, PAD, 120, W - 2 * PAD, 6, pct, color if window else NO_DATA, pal, pace)

        if window:
            left = f"{round(st.pct)} % de {WINDOW_NAMES[st.key]}"
            right = f"reinicia en {fmt_duration(st.reset_in)}" if st.reset_in is not None else "sin iniciar"
            draw_text(p, PAD, 146, left, pal["text"], f.make(10, True))
            draw_text(p, W - PAD, 146, right, pal["muted"], f.make(9), "e")
        note = other_window_note(st, ctx.limits)
        extra = f"Hoy {fmt_tokens(ctx.tokens[0])}"
        draw_text(p, PAD, 166, f"{note} · {extra}" if note else extra, pal["muted"], f.make(9))
