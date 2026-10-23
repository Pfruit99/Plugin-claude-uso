"""Pruebas del estado combinado de varios agentes (funcion pura)."""
import unittest

from claude_usage.agents import combine
from claude_usage.limits import Limits, Window
from claude_usage.providers.base import ERROR, OK, PENDIENTE, SIN_SESION, Reading
from claude_usage.status import FRENA, LIBRE, OJO, SIN_DATOS, SPANS

NOW = 1_000_000.0


def limits(pct, elapsed=0.5, key="five", updated=NOW - 5, **window):
    slot = Window(pct, NOW + SPANS[key] * (1 - elapsed), **window)
    return Limits(slot, None, updated) if key == "five" else Limits(None, slot, updated)


CLAUDE = lambda pct, **kw: ("claude", "Claude", Reading(limits(pct, **kw)))
CODEX = lambda reading: ("codex", "Codex", reading)
CODEX_MES = lambda pct: CODEX(Reading(limits(pct, key="week", span=30 * 86400, label="Mes")))


class CombineTests(unittest.TestCase):
    def test_solo_claude_es_igual_que_antes(self):
        ov = combine([CLAUDE(95)], now=NOW)
        self.assertEqual((ov.chosen, ov.status.level, ov.note), ("claude", FRENA, ""))

    def test_claude_frena_y_codex_libre_se_elige_codex(self):
        ov = combine([CLAUDE(95), CODEX_MES(10)], now=NOW)
        self.assertEqual((ov.chosen, ov.chosen_label, ov.status.level), ("codex", "Codex", LIBRE))
        self.assertEqual(ov.status.label, "Mes")
        self.assertEqual(ov.note, "Claude frena · sigue con Codex")

    def test_frena_global_solo_si_todos_frenan(self):
        ov = combine([CLAUDE(95), CODEX_MES(96)], now=NOW)
        self.assertEqual(ov.status.level, FRENA)
        self.assertEqual(ov.chosen, "claude")  # empate de nivel: manda Claude

    def test_con_igual_nivel_manda_claude_aunque_codex_tenga_menos_uso(self):
        ov = combine([CLAUDE(20), CODEX_MES(0)], now=NOW)
        self.assertEqual((ov.chosen, ov.note), ("claude", ""))  # Claude tambien esta libre: nada que advertir

    def test_claude_ojo_y_codex_libre(self):
        ov = combine([CLAUDE(75), CODEX_MES(5)], now=NOW)
        self.assertEqual(ov.note, "Claude va rápido · sigue con Codex")

    def test_agente_sin_sesion_no_cuenta(self):
        ov = combine([CLAUDE(95), CODEX(Reading(Limits(), SIN_SESION))], now=NOW)
        self.assertEqual((ov.chosen, ov.status.level), ("claude", FRENA))
        self.assertFalse(ov.entries[1].usable)

    def test_pendiente_no_cuenta(self):
        ov = combine([CLAUDE(30), CODEX(Reading(Limits(), PENDIENTE))], now=NOW)
        self.assertEqual(ov.chosen, "claude")

    def test_datos_viejos_siguen_contando_y_se_senalan(self):
        # Claude sin actividad reciente (datos de hace 1 h) no cede el sitio a Codex por estar libre ambos
        old = ("claude", "Claude", Reading(limits(30, updated=NOW - 3600)))
        ov = combine([old, CODEX_MES(0)], now=NOW)
        self.assertEqual((ov.chosen, ov.stale), ("claude", True))
        # y si los datos viejos eran de Frena, Codex fresco y libre si lo sustituye
        frena = ("claude", "Claude", Reading(limits(95, updated=NOW - 3600)))
        self.assertEqual(combine([frena, CODEX_MES(0)], now=NOW).chosen, "codex")

    def test_datos_viejos_si_no_hay_otra_cosa(self):
        old = ("claude", "Claude", Reading(limits(30, updated=NOW - 3600)))
        ov = combine([old], now=NOW)
        self.assertEqual(ov.chosen, "claude")
        self.assertTrue(ov.stale)

    def test_fallo_puntual_con_datos_sigue_contando(self):
        ov = combine([CLAUDE(95), CODEX(Reading(limits(5, key="week", span=30 * 86400, label="Mes"), ERROR))], now=NOW)
        self.assertEqual(ov.chosen, "codex")

    def test_ninguno_con_datos(self):
        ov = combine([("claude", "Claude", Reading(Limits())), CODEX(Reading(Limits(), SIN_SESION))], now=NOW)
        self.assertEqual((ov.chosen, ov.status.level), (None, SIN_DATOS))
        self.assertEqual(len(ov.entries), 2)

    def test_umbrales_configurables(self):
        self.assertEqual(combine([CLAUDE(55)], warn=50, bad=60, now=NOW).status.level, OJO)


if __name__ == "__main__":
    unittest.main()
