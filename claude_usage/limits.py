"""Lectura de los limites que escribe statusline.ps1 en ~/.claude/usage_limits.json."""
import json
import time
from dataclasses import dataclass
from pathlib import Path

LIMITS_FILE = Path.home() / ".claude" / "usage_limits.json"


@dataclass(frozen=True)
class Window:
    pct: float
    resets_at: float | None  # epoch del proximo reinicio; None si la ventana aun no empezo
    span: float | None = None   # duracion en segundos; None = la habitual de la ranura (5 h o 7 d)
    label: str | None = None    # nombre para mostrar ("Mes"); None = el habitual de la ranura


@dataclass(frozen=True)
class Limits:
    five: Window | None = None
    week: Window | None = None
    updated: float | None = None
    context: float | None = None


def read_limits(path=LIMITS_FILE, now=None):
    now = time.time() if now is None else now
    try:
        data = json.loads(Path(path).read_text("utf-8-sig"))
    except (OSError, ValueError):
        return Limits()
    if not isinstance(data, dict):
        return Limits()

    def window(key):
        w = data.get(key) or {}
        pct = w.get("used_percentage")
        if pct is None:
            return None
        resets = w.get("resets_at")
        if resets is not None and resets <= now:
            return Window(0.0, None)
        return Window(float(pct), resets)

    return Limits(window("five_hour"), window("seven_day"), data.get("updated"), data.get("context"))
