"""Contrato de los proveedores de limites: cada agente devuelve un Reading con el mismo Limits."""
from dataclasses import dataclass, field
from typing import Protocol

from ..limits import Limits

OK, SIN_SESION, NO_INSTALADO, ERROR, PENDIENTE = "ok", "sin_sesion", "no_instalado", "error", "pendiente"
STATE_TEXT = {OK: "Conectado", SIN_SESION: "Sin sesión", NO_INSTALADO: "No instalado", ERROR: "Error",
              PENDIENTE: "Consultando…"}


@dataclass(frozen=True)
class Reading:
    limits: Limits = field(default_factory=Limits)
    state: str = OK
    message: str = ""


class Provider(Protocol):
    name: str          # clave: "claude", "codex"
    label: str         # nombre para mostrar
    poll_seconds: int  # cada cuanto se consulta (solo los lentos)
    slow: bool         # True: se lee en un hilo aparte y no en cada refresco

    def configure(self, cfg: dict) -> None: ...

    def read(self) -> Reading:
        """Nunca lanza: los fallos se devuelven como Reading con su estado."""
