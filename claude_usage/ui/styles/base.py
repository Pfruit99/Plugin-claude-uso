"""Contrato comun de los estilos: cada uno calcula su Layout y lo dibuja."""
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QPointF, QRectF

from ...limits import Limits
from ...status import STALE_SECONDS, Status
from ..fx import Fx


@dataclass(frozen=True)
class Context:
    """Todo lo que un estilo necesita para calcular su tamano y dibujarse; los estilos no tocan archivos ni config."""
    limits: Limits   # con los porcentajes ya animados (para dibujar)
    real: Limits     # con los porcentajes reales (para avisos y estado)
    status: Status   # calculado con los porcentajes reales
    tokens: tuple    # (hoy, semana)
    cfg: dict
    pal: dict
    fonts: object
    hover: bool
    now: float
    fx: Fx = Fx()  # efectos de vida visual; por defecto, ninguno

    @property
    def stale(self):
        return bool(self.limits.updated) and self.now - self.limits.updated > STALE_SECONDS

    def window(self, key):
        return {"five": self.limits.five, "week": self.limits.week}.get(key)


@dataclass(frozen=True)
class Layout:
    """Tamano de la tarjeta y zonas clicables [(QRectF, accion)]; dibujo y clics usan este mismo objeto."""
    w: int
    h: int
    zones: tuple = ()

    def hit(self, x, y):
        pt = QPointF(x, y)
        return next((action for rect, action in self.zones if rect.contains(pt)), None)


class Style(Protocol):
    def layout(self, ctx: Context) -> Layout: ...

    def paint(self, p, ctx: Context, layout: Layout) -> None: ...


def gear_zone(w, size=44):
    """Zona clicable del engranaje en la esquina superior derecha."""
    return QRectF(w - size, 0, size, 40), "options"
