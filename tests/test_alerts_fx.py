"""Pruebas de los avisos de cambio de estado y de los efectos visuales (sin ventanas)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from claude_usage import config
from claude_usage.alerts import COOLDOWN, StateWatcher
from claude_usage.limits import Limits, Window
from claude_usage.status import FRENA, LIBRE, OJO, SPANS, compute_status
from claude_usage.ui.fx import BLEND_S, FLASH_S, Fx, fx_active, make_fx

_app = QApplication.instance() or QApplication([])
NOW = 1_000_000.0


def status(pct, elapsed=0.5):
    window = Window(pct, NOW + SPANS["five"] * (1 - elapsed))
    return compute_status(Limits(window), now=NOW)


LIBRE_ST, OJO_ST, FRENA_ST = status(30), status(75), status(95)


class WatcherTests(unittest.TestCase):
    def test_primera_lectura_no_avisa(self):
        self.assertIsNone(StateWatcher().update(FRENA_ST, False, NOW))

    def test_libre_a_ojo_y_a_frena(self):
        w = StateWatcher()
        w.update(LIBRE_ST, False, NOW)
        self.assertEqual(w.update(OJO_ST, False, NOW + 1).kind, "ojo")
        alert = w.update(FRENA_ST, False, NOW + 2)
        self.assertEqual((alert.kind, alert.warning), ("frena", True))

    def test_mismo_estado_no_repite(self):
        w = StateWatcher()
        w.update(OJO_ST, False, NOW)
        self.assertIsNone(w.update(OJO_ST, False, NOW + 60))

    def test_aviso_al_terminar_frena(self):
        w = StateWatcher()
        w.update(FRENA_ST, False, NOW)
        alert = w.update(LIBRE_ST, False, NOW + 5)
        self.assertEqual(alert.kind, "listo")
        self.assertIn("reiniciado", alert.message)
        w2 = StateWatcher()
        w2.update(FRENA_ST, False, NOW)
        self.assertIn("ve con calma", w2.update(OJO_ST, False, NOW + 5).message)

    def test_recuperarse_de_ojo_a_libre_no_avisa(self):
        w = StateWatcher()
        w.update(OJO_ST, False, NOW)
        self.assertIsNone(w.update(LIBRE_ST, False, NOW + 5))

    def test_sin_datos_y_datos_viejos_se_ignoran(self):
        w = StateWatcher()
        w.update(LIBRE_ST, False, NOW)
        self.assertIsNone(w.update(compute_status(Limits(), now=NOW), False, NOW + 1))
        self.assertIsNone(w.update(FRENA_ST, True, NOW + 2))
        self.assertEqual(w.update(FRENA_ST, False, NOW + 3).kind, "frena")  # el estado no se perdio

    def test_pausa_entre_avisos_del_mismo_tipo(self):
        w = StateWatcher()
        w.update(LIBRE_ST, False, NOW)
        self.assertIsNotNone(w.update(OJO_ST, False, NOW + 1))
        w.update(LIBRE_ST, False, NOW + 2)
        self.assertIsNone(w.update(OJO_ST, False, NOW + 3))
        w.update(LIBRE_ST, False, NOW + 4)
        self.assertIsNotNone(w.update(OJO_ST, False, NOW + COOLDOWN + 10))

    def test_mensaje_de_agotado(self):
        w = StateWatcher()
        w.update(LIBRE_ST, False, NOW)
        self.assertIn("agotado", w.update(status(100), False, NOW + 1).message)


class FxTests(unittest.TestCase):
    def test_sin_cambio_no_hay_fundido_ni_destello(self):
        fx = make_fx(LIBRE, None, None, NOW)
        self.assertEqual((fx.prev_level, fx.blend, fx.flash, fx.pulse), (None, 1.0, 0.0, None))

    def test_cambio_reciente(self):
        fx = make_fx(OJO, LIBRE, NOW, NOW + 0.1)
        self.assertEqual(fx.prev_level, LIBRE)
        self.assertLess(fx.blend, 1)
        self.assertGreater(fx.flash, 0.5)
        done = make_fx(OJO, LIBRE, NOW, NOW + FLASH_S + 0.1)
        self.assertEqual((done.prev_level, done.blend, done.flash), (None, 1.0, 0.0))

    def test_color_se_mezcla_durante_el_fundido(self):
        start, end = Fx(prev_level=LIBRE, blend=0.0).color(OJO), Fx(prev_level=LIBRE, blend=1.0).color(OJO)
        mid = Fx(prev_level=LIBRE, blend=0.5).color(OJO)
        self.assertNotIn(mid, (start, end))
        self.assertEqual(Fx().color(FRENA), Fx(prev_level=OJO, blend=1.0).color(FRENA))

    def test_solo_late_en_ojo_y_frena(self):
        self.assertIsNone(make_fx(LIBRE, None, None, NOW).pulse)
        for level in (OJO, FRENA):
            self.assertTrue(0.0 <= make_fx(level, None, None, NOW + 0.37).pulse <= 1.0)

    def test_cuando_hay_algo_que_animar(self):
        self.assertFalse(fx_active(LIBRE, None, NOW))
        self.assertTrue(fx_active(FRENA, None, NOW))
        self.assertTrue(fx_active(LIBRE, NOW, NOW + 0.5))
        self.assertFalse(fx_active(LIBRE, NOW, NOW + FLASH_S + 1))
        self.assertGreater(BLEND_S, 0)


class ConfigTests(unittest.TestCase):
    def test_opciones_nuevas(self):
        cfg = config.sanitize_config({"animations": "x", "notify": 0})
        self.assertEqual((cfg["animations"], cfg["notify"]), (True, False))
        self.assertTrue(config.DEFAULT_CONFIG["animations"] and config.DEFAULT_CONFIG["notify"])
        self.assertIn("animations", config.RESETTABLE)


if __name__ == "__main__":
    unittest.main()
