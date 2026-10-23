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
    with mock.patch("claude_usage.providers.claude.read_limits", return_value=Limits()), \
            mock.patch.object(card_module, "TokenCounter", FakeCounter), \
            mock.patch.object(config, "load_config", return_value=dict(config.DEFAULT_CONFIG)), \
            mock.patch.object(card_module.config, "save_config"):
        card = card_module.Card()
    card.timer.stop()
    card.minute.stop()
    # Nunca escribir en el archivo de configuracion real: el guardado es diferido y se dispararia fuera del parche.
    card.save = card.flush_save = lambda: None
    card.save_timer.timeout.disconnect()
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


class AgentsOnCardTests(unittest.TestCase):
    """La ventana lee a los agentes lentos en segundo plano, sin bloquear y solo cuando toca."""

    def setUp(self):
        from claude_usage.limits import Window
        from claude_usage.providers import PROVIDERS
        from claude_usage.providers.base import OK, Reading
        self.provider = PROVIDERS["codex"]
        mes = Window(10.0, time.time() + 20 * 86400, span=30 * 86400, label="Mes")
        self.reading = Reading(Limits(None, mes, time.time()), OK)
        patcher = mock.patch.object(self.provider, "read", return_value=self.reading)
        self.read = patcher.start()
        self.addCleanup(patcher.stop)

    def test_desactivado_no_consulta_ni_aparece(self):
        card = make_card()
        card.refresh(reschedule=False)
        pump(lambda: False, 0.3)
        self.read.assert_not_called()
        self.assertEqual([e.name for e in card.overview().entries], ["claude"])

    def test_al_activar_se_consulta_y_entra_en_el_estado(self):
        card = make_card()
        card.apply("codex_enabled", True)
        pump(lambda: "codex" in card.readings)
        self.assertEqual(card.readings["codex"], self.reading)
        self.assertEqual([e.name for e in card.overview().entries], ["claude", "codex"])
        self.assertEqual(card.agent_state_text("codex"), "Conectado")
        self.assertIn("Codex", card.tooltip())

    def test_al_desactivar_se_olvida_la_lectura(self):
        card = make_card()
        card.apply("codex_enabled", True)
        pump(lambda: "codex" in card.readings)
        card.apply("codex_enabled", False)
        self.assertNotIn("codex", card.readings)
        self.assertEqual(card.agent_state_text("codex"), "Desactivado")

    def test_no_consulta_si_el_widget_no_esta_visible_salvo_manual(self):
        card = make_card()
        card.cfg["codex_enabled"] = True       # activado, pero la ventana nunca se mostro
        card.refresh()                         # refresco automatico: no consulta
        pump(lambda: False, 0.3)
        self.read.assert_not_called()
        card.refresh(reschedule=False)         # "Actualizar ahora": si consulta
        pump(lambda: "codex" in card.readings)
        self.read.assert_called_once()

    def test_no_lanza_dos_consultas_a_la_vez(self):
        import threading
        gate = threading.Event()
        self.read.side_effect = lambda: (gate.wait(2), self.reading)[1]
        card = make_card()
        card.cfg["codex_enabled"] = True
        card._poll_agents(force=True)
        card._poll_agents(force=True)
        gate.set()
        pump(lambda: "codex" in card.readings)
        self.assertEqual(self.read.call_count, 1)

    def test_claude_frena_y_codex_libre_el_estado_es_el_de_codex(self):
        from claude_usage.limits import Window
        card = make_card()
        card.limits = Limits(Window(100.0, time.time() + 3600), None, time.time())
        card.apply("codex_enabled", True)
        pump(lambda: "codex" in card.readings)
        ov = card.overview()
        self.assertEqual((ov.chosen, ov.status.level), ("codex", "libre"))
        self.assertIn("sigue con Codex", ov.note)
