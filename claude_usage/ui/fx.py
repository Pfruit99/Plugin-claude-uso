"""Efectos de vida visual: fundido al cambiar de estado, destello del borde y latido de la luz."""
import math
from dataclasses import dataclass

from PySide6.QtGui import QColor

from ..status import FRENA, OJO
from .theme import STATUS_COLOR

BLEND_S = 0.45  # fundido de color y palabra
FLASH_S = 1.1   # destello del borde
PULSE_PERIOD = {OJO: 2.4, FRENA: 1.1}  # segundos por latido; Libre queda quieto


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(*(round(x + (y - x) * t) for x, y in ((ca.red(), cb.red()), (ca.green(), cb.green()),
                                                         (ca.blue(), cb.blue())))).name()


@dataclass(frozen=True)
class Fx:
    prev_level: str | None = None
    blend: float = 1.0        # 0 -> 1 durante el fundido
    flash: float = 0.0        # 1 -> 0 durante el destello
    pulse: float | None = None  # 0..1 del latido; None si la luz no late

    def color(self, level):
        """Color del estado, mezclado con el anterior mientras dura el fundido."""
        color = STATUS_COLOR[level]
        if self.prev_level is None or self.blend >= 1:
            return color
        return mix(STATUS_COLOR[self.prev_level], color, self.blend)


def make_fx(level, prev_level, changed_at, now):
    t = None if changed_at is None else now - changed_at
    period = PULSE_PERIOD.get(level)
    return Fx(
        prev_level=prev_level if t is not None and t < BLEND_S else None,
        blend=1.0 if t is None else smooth(t / BLEND_S),
        flash=0.0 if t is None else max(0.0, 1 - t / FLASH_S) ** 2,
        pulse=None if period is None else 0.5 - 0.5 * math.cos(2 * math.pi * (now % period) / period),
    )


def fx_active(level, changed_at, now):
    """True mientras haya algo que animar: un cambio reciente o una luz que late."""
    return level in PULSE_PERIOD or (changed_at is not None and now - changed_at < FLASH_S)
