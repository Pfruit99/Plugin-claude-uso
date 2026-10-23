"""Pruebas de la ventana principal con datos y configuracion simulados (no toca archivos del usuario)."""
import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from claude_usage import config
from claude_usage.limits import Limits

_app = QApplication.instance() or QApplication([])


class FakeCounter:
    def totals(self, week_start):
        return 0, 0


def make_card():
    from claude_usage.ui import card as card_module
    with mock.patch.object(card_module, "read_limits", return_value=Limits()), \
            mock.patch.object(card_module, "TokenCounter", FakeCounter), \
            mock.patch.object(config, "load_config", return_value=dict(config.DEFAULT_CONFIG)), \
            mock.patch.object(card_module.config, "save_config"):
        card = card_module.Card()
    card.timer.stop()
    card.minute.stop()
    return card


def pump(until, timeout=2.0):
    end = time.time() + timeout
    while not until() and time.time() < end:
        _app.processEvents()
        _app.sendPostedEvents(None, QEvent.DeferredDelete)
        time.sleep(0.01)


class CardTests(unittest.TestCase):
    def test_ajustes_se_puede_abrir_cerrar_y_volver_a_abrir(self):
        card = make_card()
        card.open_settings()
        first = card._settings
        self.assertTrue(first.isVisible())
        first.close()
        pump(lambda: card._settings is None)
        self.assertIsNone(card._settings)
        card.open_settings()  # antes fallaba: la ventana anterior ya estaba borrada
        self.assertIsNotNone(card._settings)
        self.assertIsNot(card._settings, first)

    def test_abrir_ajustes_dos_veces_seguidas_reutiliza_la_ventana(self):
        card = make_card()
        card.open_settings()
        first = card._settings
        card.open_settings()
        self.assertIs(card._settings, first)


if __name__ == "__main__":
    unittest.main()
