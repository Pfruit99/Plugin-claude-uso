"""Pruebas de los estilos: tamano, zonas clicables y que todos los estados se dibujan sin errores."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claude_usage import config
from claude_usage.agents import combine
from claude_usage.limits import Limits, Window
from claude_usage.providers.base import SIN_SESION, Reading
from claude_usage.status import SPANS, compute_status
from claude_usage.ui.fonts import Fonts
from claude_usage.ui.styles import STYLES
from claude_usage.ui.styles.base import Context
from claude_usage.ui.theme import THEMES

NOW = 1_000_000.0
_app = QApplication.instance() or QApplication([])


def limits(p5, e5, pw, ew):
    return Limits(Window(p5, NOW + SPANS["five"] * (1 - e5)), Window(pw, NOW + SPANS["week"] * (1 - ew)), NOW - 5, 40)


CASES = {"libre": limits(38, .55, 21, .3), "ojo": limits(52, .25, 30, .4), "frena": limits(100, .6, 60, .5),
         "sin_datos": Limits()}


def context(lim, style, hover=False, **cfg):
    full = dict(config.DEFAULT_CONFIG, style=style, **cfg)
    return Context(limits=lim, real=lim, status=compute_status(lim, full["warn"], full["bad"], NOW), tokens=(1200, 34000),
                   cfg=full, pal=THEMES["dark"], fonts=Fonts(), hover=hover, now=NOW)


def multi_context(items, style, hover=False):
    """Contexto con varios agentes, como lo arma Card: dibuja el agente elegido."""
    cfg = dict(config.DEFAULT_CONFIG, style=style)
    ov = combine(items, cfg["warn"], cfg["bad"], NOW)
    chosen = ov.chosen_entry or ov.entries[0]
    return Context(limits=chosen.limits, real=chosen.limits, status=ov.status, tokens=(1200, 34000), cfg=cfg,
                   pal=THEMES["dark"], fonts=Fonts(), hover=hover, now=NOW, overview=ov,
                   claude=ov.entries[0].limits)


MES = Window(10.0, NOW + 20 * 86400, span=30 * 86400, label="Mes")
AGENTS = {
    "claude frena, codex libre": [("claude", "Claude", Reading(CASES["frena"])),
                                  ("codex", "Codex", Reading(Limits(None, MES, NOW - 5)))],
    "codex sin sesion": [("claude", "Claude", Reading(CASES["libre"])), ("codex", "Codex", Reading(Limits(), SIN_SESION))],
    "solo claude": [("claude", "Claude", Reading(CASES["ojo"]))],
}


class StyleTests(unittest.TestCase):
    def test_los_estilos_coinciden_con_las_opciones(self):
        self.assertEqual(set(STYLES), {v for _, v in config.STYLE_CHOICES})

    def test_todos_los_estilos_se_dibujan_en_todos_los_estados(self):
        for name, style in STYLES.items():
            for case, lim in CASES.items():
                for hover in (False, True):
                    ctx = context(lim, name, hover)
                    layout = style.layout(ctx)
                    self.assertGreater(layout.w, 100, (name, case))
                    self.assertGreater(layout.h, 30, (name, case))
                    img = QImage(layout.w + 40, layout.h + 40, QImage.Format_ARGB32)
                    img.fill(0)
                    p = QPainter(img)
                    p.translate(14, 14)
                    style.paint(p, ctx, layout)
                    p.end()

    def test_todos_los_estilos_se_dibujan_con_varios_agentes(self):
        for name, style in STYLES.items():
            for case, items in AGENTS.items():
                for hover in (False, True):
                    ctx = multi_context(items, name, hover)
                    layout = style.layout(ctx)
                    img = QImage(layout.w + 40, layout.h + 40, QImage.Format_ARGB32)
                    img.fill(0)
                    p = QPainter(img)
                    p.translate(14, 14)
                    style.paint(p, ctx, layout)
                    p.end()

    def test_pildora_nombra_al_agente_elegido(self):
        from claude_usage.texts import pill_text
        ctx = multi_context(AGENTS["claude frena, codex libre"], "pildora")
        self.assertEqual(ctx.agent_name, "Codex")
        self.assertTrue(pill_text(ctx.status, ctx.agent_name).endswith("· Codex"))
        self.assertIsNone(multi_context(AGENTS["solo claude"], "pildora").agent_name)

    def test_pildora_con_varios_agentes_crece_al_desplegarse(self):
        one = STYLES["pildora"].layout(multi_context(AGENTS["solo claude"], "pildora", hover=True))
        two = STYLES["pildora"].layout(multi_context(AGENTS["claude frena, codex libre"], "pildora", hover=True))
        self.assertGreater(two.h, one.h)

    def test_clasico_sigue_mirando_solo_a_claude(self):
        ctx = multi_context(AGENTS["claude frena, codex libre"], "clasico")
        self.assertEqual(ctx.status.label, "Mes")             # el estado global es el de Codex...
        view = ctx.claude_view()
        self.assertEqual(view.status.label, "5 h")            # ...pero Clasico dibuja Claude
        self.assertEqual(view.real, ctx.overview.entries[0].limits)

    def test_las_zonas_clicables_caben_en_la_tarjeta(self):
        for name, style in STYLES.items():
            layout = style.layout(context(CASES["libre"], name))
            for rect, action in layout.zones:
                self.assertIn(action, ("options", "refresh"))
                self.assertGreaterEqual(rect.left(), 0)
                self.assertLessEqual(rect.right(), layout.w + 1)

    def test_el_engranaje_abre_las_opciones(self):
        for name in ("semaforo", "margen"):
            layout = STYLES[name].layout(context(CASES["libre"], name))
            self.assertEqual(layout.hit(layout.w - 20, 20), "options")
        self.assertEqual(STYLES["clasico"].layout(context(CASES["libre"], "clasico")).hit(18 + 120, 20), "options")

    def test_clasico_refresca_solo_en_tamano_completo(self):
        full = STYLES["clasico"].layout(context(CASES["libre"], "clasico", size="full"))
        compact = STYLES["clasico"].layout(context(CASES["libre"], "clasico", size="compact"))
        self.assertEqual(full.hit(full.w - 40, 20), "refresh")
        self.assertIsNone(compact.hit(20, 20))

    def test_clasico_crece_con_el_aviso_de_agotado(self):
        normal = STYLES["clasico"].layout(context(CASES["libre"], "clasico"))
        agotado = STYLES["clasico"].layout(context(CASES["frena"], "clasico"))
        self.assertEqual(agotado.h - normal.h, 38)

    def test_pildora_se_despliega_con_el_raton(self):
        small = STYLES["pildora"].layout(context(CASES["libre"], "pildora"))
        big = STYLES["pildora"].layout(context(CASES["libre"], "pildora", hover=True))
        self.assertLess(small.h, big.h)
        self.assertGreaterEqual(big.w, small.w)


if __name__ == "__main__":
    unittest.main()
