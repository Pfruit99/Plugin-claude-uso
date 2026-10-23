"""Pruebas de la logica sin interfaz: estado, configuracion, formatos, textos, limites y tokens."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_usage import config, formatting, texts
from claude_usage.limits import Limits, Window, read_limits
from claude_usage.status import FRENA, LIBRE, OJO, SIN_DATOS, SPANS, compute_status
from claude_usage.tokens import TokenCounter

NOW = 1_000_000.0


def window(pct, elapsed=None, key="five"):
    """Ventana con `pct` de uso y `elapsed` (0-1) de su duracion ya transcurrida."""
    resets = None if elapsed is None else NOW + SPANS[key] * (1 - elapsed)
    return Window(pct, resets)


class StatusTests(unittest.TestCase):
    def test_sin_datos(self):
        self.assertEqual(compute_status(Limits(), now=NOW).level, SIN_DATOS)

    def test_libre_si_va_por_debajo_del_ritmo(self):
        st = compute_status(Limits(window(38, 0.55), window(21, 0.3, "week")), now=NOW)
        self.assertEqual(st.level, LIBRE)
        self.assertGreater(st.margin, 0)
        self.assertAlmostEqual(st.margin, (0.55 - 0.38) * SPANS["five"])

    def test_ojo_por_ritmo_aunque_el_porcentaje_sea_bajo(self):
        st = compute_status(Limits(window(40, 0.2)), now=NOW)
        self.assertEqual(st.level, OJO)
        self.assertLess(st.margin, 0)

    def test_ojo_por_umbral(self):
        self.assertEqual(compute_status(Limits(window(72, 0.9)), now=NOW).level, OJO)

    def test_tolerancia_de_ritmo(self):
        self.assertEqual(compute_status(Limits(window(30, 0.21)), now=NOW).level, LIBRE)

    def test_frena_por_umbral_y_agotado(self):
        self.assertEqual(compute_status(Limits(window(91, 0.95)), now=NOW).level, FRENA)
        st = compute_status(Limits(window(100, 0.5)), now=NOW)
        self.assertEqual((st.level, st.exhausted), (FRENA, True))

    def test_sin_hora_de_reinicio_solo_cuentan_los_umbrales(self):
        st = compute_status(Limits(window(40)), now=NOW)
        self.assertEqual((st.level, st.margin), (LIBRE, None))

    def test_gana_la_ventana_peor(self):
        st = compute_status(Limits(window(10, 0.5), window(95, 0.5, "week")), now=NOW)
        self.assertEqual((st.level, st.key), (FRENA, "week"))

    def test_umbrales_de_configuracion(self):
        self.assertEqual(compute_status(Limits(window(55, 0.9)), warn=50, bad=60, now=NOW).level, OJO)


class ConfigTests(unittest.TestCase):
    def test_valores_invalidos_vuelven_al_defecto(self):
        cfg = config.sanitize_config(dict(style="x", view=3, size=None, theme="rojo", refresh="a",
                                          opacity=500, warn=99, bad=1, x="a", panel_x=True))
        d = config.DEFAULT_CONFIG
        self.assertEqual((cfg["style"], cfg["view"], cfg["size"], cfg["theme"]),
                         (d["style"], d["view"], d["size"], d["theme"]))
        self.assertEqual((cfg["refresh"], cfg["opacity"]), (d["refresh"], 100))
        self.assertLess(cfg["warn"], cfg["bad"])
        self.assertIsNone(cfg["x"])
        self.assertIsNone(cfg["panel_x"])

    def test_estilo_valido_se_conserva(self):
        for _, value in config.STYLE_CHOICES:
            self.assertEqual(config.sanitize_config({"style": value})["style"], value)

    def test_guardar_y_cargar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            cfg = dict(config.DEFAULT_CONFIG, style="pildora", x=10)
            config.save_config(cfg, path)
            self.assertEqual(config.load_config(path)["style"], "pildora")
            self.assertEqual(config.load_config(Path(tmp) / "no-existe.json"), config.DEFAULT_CONFIG)

    def test_config_antigua_sin_estilo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"view": "bar", "size": "compact"}), "utf-8")
            cfg = config.load_config(path)
            self.assertEqual((cfg["style"], cfg["view"]), ("semaforo", "bar"))


class FormattingTests(unittest.TestCase):
    def test_duraciones(self):
        self.assertEqual(formatting.fmt_duration(30), "1 min")
        self.assertEqual(formatting.fmt_duration(3720), "1 h 2 min")
        self.assertEqual(formatting.fmt_duration(90_000), "1 d 1 h")

    def test_tokens(self):
        self.assertEqual(formatting.fmt_tokens(950), "950")
        self.assertEqual(formatting.fmt_tokens(12_400), "12k")
        self.assertEqual(formatting.fmt_tokens(1_250_000), "1,2M")

    def test_remaining_y_ago(self):
        self.assertEqual(formatting.fmt_remaining(None), "sin dato")
        self.assertEqual(formatting.fmt_remaining(Window(0, None)), "sin iniciar")
        self.assertEqual(formatting.fmt_remaining(Window(0, NOW + 600), NOW), "10 min")
        self.assertEqual(formatting.fmt_ago(NOW - 10, NOW), "ahora")
        self.assertEqual(formatting.fmt_ago(NOW - 600, NOW), "hace 10 min")


class TextTests(unittest.TestCase):
    def test_margen_positivo_y_negativo(self):
        ok = compute_status(Limits(window(38, 0.55)), now=NOW)
        self.assertEqual(texts.margin_parts(ok)[0], "Te sobra")
        fast = compute_status(Limits(window(50, 0.2)), now=NOW)
        self.assertEqual(texts.margin_parts(fast)[0], "Vas")

    def test_sin_uso_no_presume_de_margen(self):
        st = compute_status(Limits(window(0, 0.4)), now=NOW)
        self.assertEqual(texts.margin_parts(st), ("Sin uso", "0 %", "en 5 h"))
        mes = Limits(week=Window(0.0, NOW + 20 * 86400, span=30 * 86400, label="Mes"))
        self.assertEqual(texts.margin_parts(compute_status(mes, now=NOW))[2], "en Mes")

    def test_agotado(self):
        st = compute_status(Limits(window(100, 0.9)), now=NOW)
        self.assertEqual(texts.margin_parts(st)[0], "Vuelve en")
        self.assertIn("agotado", texts.hint(st))
        self.assertTrue(texts.pill_text(st).startswith("Frena"))

    def test_sin_datos(self):
        st = compute_status(Limits(), now=NOW)
        self.assertEqual(texts.pill_text(st), "Sin datos")
        self.assertEqual(texts.other_window_note(st, Limits()), "")

    def test_nota_de_la_otra_ventana(self):
        limits = Limits(window(38, 0.55), window(21, 0.3, "week"))
        st = compute_status(limits, now=NOW)
        self.assertEqual(texts.other_window_note(st, limits), "Semana: 21 % · normal")


class LimitsTests(unittest.TestCase):
    def test_lee_y_detecta_ventana_reiniciada(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l.json"
            path.write_text(json.dumps({
                "five_hour": {"used_percentage": 40, "resets_at": NOW - 5},
                "seven_day": {"used_percentage": 20, "resets_at": NOW + 100},
                "updated": 5, "context": 12}), "utf-8-sig")
            limits = read_limits(path, now=NOW)
            self.assertEqual(limits.five, Window(0.0, None))
            self.assertEqual(limits.week, Window(20.0, NOW + 100))
            self.assertEqual((limits.updated, limits.context), (5, 12))

    def test_archivo_ausente_o_roto(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_limits(Path(tmp) / "no.json"), Limits())
            bad = Path(tmp) / "bad.json"
            bad.write_text("[1, 2]", "utf-8")
            self.assertEqual(read_limits(bad), Limits())


class TokenTests(unittest.TestCase):
    def test_lectura_incremental(self):
        now = datetime.now(timezone.utc)

        def line(msg_id, tokens, when=now):
            return json.dumps({"type": "assistant", "timestamp": when.isoformat().replace("+00:00", "Z"),
                               "requestId": "r", "message": {"id": msg_id, "usage": {
                                   "input_tokens": tokens, "output_tokens": 0}}}) + "\n"

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "a.jsonl"
            log.write_text(line("m1", 100) + line("m1", 150) + line("m2", 50), "utf-8")
            counter = TokenCounter(tmp)
            week_start = (now - timedelta(days=3)).astimezone()
            self.assertEqual(counter.totals(week_start), (200, 200))  # m1 cuenta una sola vez (el mayor)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(line("m3", 10))
            self.assertEqual(counter.totals(week_start), (210, 210))
            old = line("m4", 999, now - timedelta(days=10))
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(old)
            self.assertEqual(counter.totals(week_start), (210, 210))


if __name__ == "__main__":
    unittest.main()
