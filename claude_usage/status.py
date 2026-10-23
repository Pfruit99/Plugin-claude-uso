"""Estado del uso (Libre / Ojo / Frena) calculado por ritmo: uso frente a tiempo transcurrido."""
import time
from dataclasses import dataclass, field

LIBRE, OJO, FRENA, SIN_DATOS = "libre", "ojo", "frena", "sin_datos"
SPANS = {"five": 5 * 3600, "week": 7 * 86400}
PACE_TOLERANCE = 0.10  # cuanto puede ir el uso por delante del tiempo antes de pasar a "Ojo"
STALE_SECONDS = 15 * 60
DEFAULT_LABELS = {"five": "5 h", "week": "Semana"}
RANK = {LIBRE: 0, OJO: 1, FRENA: 2}


def window_span(key, window):
    return window.span or SPANS[key]


def window_label(key, window):
    return window.label or DEFAULT_LABELS[key]


@dataclass(frozen=True)
class Status:
    level: str
    key: str | None = None            # ranura de la ventana que decide: "five", "week" o None
    label: str | None = None          # nombre de esa ventana ("5 h", "Semana", "Mes")
    levels: dict = field(default_factory=dict)  # nivel de cada ventana con datos
    pct: float | None = None          # uso de la ventana que decide
    margin: float | None = None       # segundos de margen frente al ritmo (negativo = vas por delante)
    reset_in: float | None = None     # segundos hasta el reinicio de la ventana que decide
    exhausted: bool = False


def pace_fraction(window, span, now=None):
    """Fraccion de la ventana ya transcurrida (None si no se conoce el reinicio)."""
    if window is None or window.resets_at is None:
        return None
    now = time.time() if now is None else now
    return max(0.0, min(1.0, 1 - (window.resets_at - now) / span))


def window_level(window, span, warn, bad, now=None):
    if window.pct >= bad:
        return FRENA
    pace = pace_fraction(window, span, now)
    if window.pct >= warn or (pace is not None and window.pct / 100 > pace + PACE_TOLERANCE):
        return OJO
    return LIBRE


def compute_status(limits, warn=70, bad=90, now=None):
    now = time.time() if now is None else now
    levels, best = {}, None
    for key, window in (("five", limits.five), ("week", limits.week)):
        if window is None:
            continue
        levels[key] = window_level(window, window_span(key, window), warn, bad, now)
        rank = (RANK[levels[key]], window.pct)
        if best is None or rank > best[0]:
            best = (rank, key, window)
    if best is None:
        return Status(SIN_DATOS)
    _, key, window = best
    span = window_span(key, window)
    pace = pace_fraction(window, span, now)
    return Status(
        level=levels[key], key=key, label=window_label(key, window), levels=levels, pct=window.pct,
        margin=None if pace is None else (pace - window.pct / 100) * span,
        reset_in=None if window.resets_at is None else max(0.0, window.resets_at - now),
        exhausted=any(w is not None and w.pct >= 100 for w in (limits.five, limits.week)),
    )
