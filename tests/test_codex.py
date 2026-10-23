"""Pruebas de Codex: analizador con la respuesta real capturada y cliente contra un servidor de pruebas."""
import copy
import ctypes
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from claude_usage.limits import Limits
from claude_usage.providers import codex
from claude_usage.providers.base import ERROR, NO_INSTALADO, OK, SIN_SESION
from claude_usage.providers.codex import CodexClient, CodexError, CodexProvider, label_for, parse_rate_limits
from claude_usage.status import LIBRE, compute_status

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "codex_rate_limits_free.json"   # captura REAL (plan free), sin accountId
FAKE = HERE / "fake_codex_server.py"
REAL = json.loads(FIXTURE.read_text("utf-8"))["result"]
NOW = REAL["rateLimits"]["primary"]["resetsAt"] - 20 * 86400  # 20 dias antes del reinicio capturado


def fake_client(mode, timeout=15.0, pidfile=None):
    env = {"FAKE_CODEX_MODE": mode, "FAKE_CODEX_FIXTURE": str(FIXTURE)}
    if pidfile:
        env["FAKE_CODEX_PIDFILE"] = str(pidfile)
    patcher = mock.patch.dict(os.environ, env)
    patcher.start()
    return CodexClient([sys.executable, str(FAKE)], timeout=timeout), patcher


def pid_alive(pid):
    """True si el proceso sigue en ejecucion (API de Windows; no envia ninguna senal al proceso)."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


class ParseTests(unittest.TestCase):
    def test_plan_free_una_ventana_de_30_dias(self):
        limits = parse_rate_limits(REAL, NOW)
        self.assertIsNone(limits.five)
        self.assertEqual((limits.week.pct, limits.week.label, limits.week.span), (0.0, "Mes", 43200 * 60))
        self.assertEqual(limits.week.resets_at, REAL["rateLimits"]["primary"]["resetsAt"])

    def test_estado_con_la_captura_real(self):
        status = compute_status(parse_rate_limits(REAL, NOW), now=NOW)
        self.assertEqual((status.level, status.label, status.key), (LIBRE, "Mes", "week"))
        self.assertAlmostEqual(status.reset_in, 20 * 86400)

    def test_ventana_reiniciada(self):
        limits = parse_rate_limits(REAL, REAL["rateLimits"]["primary"]["resetsAt"] + 1)
        self.assertEqual((limits.week.pct, limits.week.resets_at, limits.week.label), (0.0, None, "Mes"))

    def test_dos_ventanas_se_reparten_por_duracion(self):
        # Forma alterada a proposito sobre la captura real: se anade `secondary` de 5 h (no es una captura real).
        data = copy.deepcopy(REAL)
        snap = data["rateLimits"]
        snap["secondary"] = snap["primary"]
        snap["primary"] = {"usedPercent": 40, "windowDurationMins": 300, "resetsAt": NOW + 3600}
        limits = parse_rate_limits(data, NOW)
        self.assertEqual((limits.five.label, limits.five.pct), ("5 h", 40.0))
        self.assertEqual(limits.week.label, "Mes")

    def test_sin_ventanas_o_forma_inesperada(self):
        self.assertEqual(parse_rate_limits({}, NOW), Limits(None, None, NOW, None))
        self.assertEqual(parse_rate_limits({"rateLimits": {"primary": {"usedPercent": None}}}, NOW).week, None)

    def test_usa_rate_limits_by_limit_id_si_falta_la_vista_simple(self):
        data = {"rateLimitsByLimitId": {"codex": REAL["rateLimits"]}}
        self.assertEqual(parse_rate_limits(data, NOW).week.label, "Mes")

    def test_etiquetas(self):
        self.assertEqual([label_for(m) for m in (300, 10080, 43200, 2880, 120, 45)],
                         ["5 h", "Semana", "Mes", "2 d", "2 h", "45 min"])


class ClientTests(unittest.TestCase):
    def run_client(self, mode, **kw):
        client, patcher = fake_client(mode, **kw)
        self.addCleanup(patcher.stop)
        return client.read_rate_limits()

    def test_lectura_correcta(self):
        self.assertEqual(self.run_client("ok")["rateLimits"]["primary"]["windowDurationMins"], 43200)

    def test_ignora_notificaciones_intermedias(self):
        self.assertIn("rateLimits", self.run_client("noisy"))

    def test_sin_sesion(self):
        with self.assertRaises(CodexError) as ctx:
            self.run_client("nologin")
        self.assertEqual(ctx.exception.state, SIN_SESION)

    def test_error_generico(self):
        with self.assertRaises(CodexError) as ctx:
            self.run_client("error")
        self.assertEqual((ctx.exception.state, ctx.exception.message), (ERROR, "boom"))

    def test_proceso_que_muere(self):
        with self.assertRaises(CodexError) as ctx:
            self.run_client("die")
        self.assertEqual(ctx.exception.state, ERROR)

    def test_tiempo_agotado_mata_el_proceso(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "pid"
            started = time.monotonic()
            with self.assertRaises(CodexError) as ctx:
                self.run_client("hang", timeout=1.5, pidfile=pidfile)
            self.assertLess(time.monotonic() - started, 8)
            self.assertIn("a tiempo", ctx.exception.message)
            time.sleep(0.3)
            self.assertFalse(pid_alive(int(pidfile.read_text())), "el proceso de prueba debe haberse terminado")

    def test_binario_inexistente(self):
        with self.assertRaises(CodexError) as ctx:
            CodexClient([str(HERE / "no-existe.exe")]).read_rate_limits()
        self.assertEqual(ctx.exception.state, NO_INSTALADO)


class ProviderTests(unittest.TestCase):
    def provider(self, mode):
        client, patcher = fake_client(mode, timeout=3)
        self.addCleanup(patcher.stop)
        for p in (mock.patch.object(codex, "find_codex", return_value=Path("codex")),
                  mock.patch.object(codex, "CodexClient", lambda command: client)):
            p.start()
            self.addCleanup(p.stop)
        return CodexProvider()

    def test_lectura_ok(self):
        reading = self.provider("ok").read()
        self.assertEqual(reading.state, OK)
        self.assertEqual(reading.limits.week.label, "Mes")

    def test_sin_sesion_no_inventa_datos(self):
        reading = self.provider("nologin").read()
        self.assertEqual((reading.state, reading.limits), (SIN_SESION, Limits()))

    def test_un_fallo_puntual_conserva_el_ultimo_dato(self):
        provider = self.provider("ok")
        good = provider.read()
        os.environ["FAKE_CODEX_MODE"] = "error"
        failed = provider.read()
        self.assertEqual((failed.state, failed.limits), (ERROR, good.limits))

    def test_no_instalado(self):
        with mock.patch.object(codex, "find_codex", return_value=None):
            reading = CodexProvider().read()
        self.assertEqual((reading.state, reading.limits), (NO_INSTALADO, Limits()))


if __name__ == "__main__":
    unittest.main()
