"""Configuracion del usuario: valores por defecto, validacion y guardado en disco."""
import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".claude-usage-widget.json"

STYLE_CHOICES = (("Semáforo", "semaforo"), ("Margen", "margen"), ("Píldora", "pildora"), ("Clásico", "clasico"))
THEME_CHOICES = (("Seguir a Windows", "auto"), ("Claro", "light"), ("Oscuro", "dark"))
REFRESH_CHOICES = (("5 s", 5), ("15 s", 15), ("30 s", 30), ("60 s", 60))

DEFAULT_CONFIG = dict(style="semaforo", view="ring", size="full", theme="auto", topmost=True, x=None, y=None,
                      panel_x=None, panel_y=None, refresh=15, warn=70, bad=90, opacity=100)
RESETTABLE = ("style", "view", "size", "theme", "topmost", "refresh", "warn", "bad", "opacity")


def _int_in(value, lo, hi, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(max(lo, min(hi, value)))


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def sanitize_config(cfg):
    """Valida rangos y tipos; lo invalido vuelve al valor por defecto."""
    d = DEFAULT_CONFIG
    if cfg.get("style") not in {v for _, v in STYLE_CHOICES}:
        cfg["style"] = d["style"]
    if cfg.get("view") not in ("ring", "bar"):
        cfg["view"] = d["view"]
    if cfg.get("size") not in ("compact", "full"):
        cfg["size"] = d["size"]
    if cfg.get("theme") not in {v for _, v in THEME_CHOICES}:
        cfg["theme"] = d["theme"]
    cfg["topmost"] = bool(cfg.get("topmost", d["topmost"]))
    cfg["refresh"] = _int_in(cfg.get("refresh"), 5, 300, d["refresh"])
    cfg["opacity"] = _int_in(cfg.get("opacity"), 30, 100, d["opacity"])
    cfg["warn"] = _int_in(cfg.get("warn"), 1, 98, d["warn"])
    cfg["bad"] = _int_in(cfg.get("bad"), cfg["warn"] + 1, 100, max(d["bad"], cfg["warn"] + 1))
    for key in ("x", "y", "panel_x", "panel_y"):
        cfg[key] = _int_or_none(cfg.get(key))
    return cfg


def load_config(path=CONFIG_FILE):
    try:
        data = json.loads(Path(path).read_text("utf-8-sig"))
        return sanitize_config({**DEFAULT_CONFIG, **(data if isinstance(data, dict) else {})})
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg, path=CONFIG_FILE):
    try:
        Path(path).write_text(json.dumps(cfg), "utf-8")
    except OSError:
        pass
