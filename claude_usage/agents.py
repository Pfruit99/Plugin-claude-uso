"""Combina los limites de varios agentes en un unico estado: el del mejor agente disponible."""
import time
from dataclasses import dataclass

from .limits import Limits
from .providers.base import ERROR, OK
from .status import FRENA, OJO, RANK, SIN_DATOS, STALE_SECONDS, Status, compute_status

_VERBS = {OJO: "va rápido", FRENA: "frena"}


@dataclass(frozen=True)
class AgentEntry:
    name: str
    label: str
    limits: Limits
    state: str
    status: Status
    usable: bool   # tiene datos y su estado es Conectado (o un fallo puntual con datos)
    stale: bool    # datos con mas de 15 minutos


@dataclass(frozen=True)
class Overview:
    status: Status            # el del agente elegido; SIN_DATOS si ninguno tiene datos
    chosen: str | None        # nombre del agente elegido
    chosen_label: str | None
    entries: tuple            # AgentEntry de todos los agentes activos
    note: str = ""            # p. ej. "Claude frena · sigue con Codex"
    stale: bool = False       # los datos del agente elegido estan desactualizados

    @property
    def chosen_entry(self):
        return next((e for e in self.entries if e.name == self.chosen), None)


def combine(items, warn=70, bad=90, now=None):
    """`items` = [(nombre, etiqueta, Reading)], con Claude primero.

    Elegido = el agente usable con mejor nivel (Libre < Ojo < Frena). Con empate de nivel gana el primero de la
    lista (Claude): solo se pasa a otro agente si esta en un nivel estrictamente mejor. Los agentes sin sesion o
    sin datos no cuentan; los datos con mas de 15 minutos si cuentan, pero `Overview.stale` lo senala.
    """
    now = time.time() if now is None else now
    entries = []
    for name, label, reading in items:
        status = compute_status(reading.limits, warn, bad, now)
        updated = reading.limits.updated
        entries.append(AgentEntry(
            name, label, reading.limits, reading.state, status,
            usable=status.level != SIN_DATOS and reading.state in (OK, ERROR),
            stale=bool(updated) and now - updated > STALE_SECONDS))
    pool = usable = [e for e in entries if e.usable]  # los datos viejos siguen contando: solo se marcan como tales
    if not pool:
        return Overview(Status(SIN_DATOS), None, None, tuple(entries))
    best = min(pool, key=lambda e: RANK[e.status.level])  # min conserva el primero en caso de empate
    claude = next((e for e in usable if e.name == "claude"), None)
    note = ""
    if claude and best.name != "claude" and RANK[claude.status.level] > RANK[best.status.level]:
        note = f"{claude.label} {_VERBS[claude.status.level]} · sigue con {best.label}"
    return Overview(best.status, best.name, best.label, tuple(entries), note, best.stale)
