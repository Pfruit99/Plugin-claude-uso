"""Avisos al cambiar de estado: decide cuando avisar y que decir, sin depender de Windows ni de Qt."""
from dataclasses import dataclass

from .formatting import fmt_duration
from .status import FRENA, LIBRE, OJO, SIN_DATOS
from .texts import WINDOW_NAMES, hint

COOLDOWN = 600  # segundos minimos entre dos avisos del mismo tipo


@dataclass(frozen=True)
class Alert:
    kind: str       # "ojo", "frena" o "listo"
    title: str
    message: str
    warning: bool   # True para el icono de advertencia


def build_alert(kind, status):
    name = WINDOW_NAMES.get(status.key, "")
    if kind == "ojo":
        return Alert(kind, "Ojo con el uso", f"{hint(status)} · {round(status.pct)} % de {name}", False)
    if kind == "frena":
        if status.exhausted:
            return Alert(kind, "Frena un momento", hint(status), True)
        reset = f" · reinicia en {fmt_duration(status.reset_in)}" if status.reset_in is not None else ""
        return Alert(kind, "Frena un momento", f"Casi sin cupo en {name}{reset}", True)
    message = "El límite se ha reiniciado" if status.level == LIBRE else "Hay cupo otra vez, ve con calma"
    return Alert("listo", "Ya puedes seguir trabajando", message, False)


class StateWatcher:
    """Compara cada lectura con la anterior y devuelve un Alert cuando el estado empeora o se recupera.

    Avisa al pasar a Ojo (desde Libre), a Frena, y cuando Frena termina. No avisa en la primera lectura,
    sin datos, con datos desactualizados ni repitiendo el mismo tipo de aviso dentro de COOLDOWN.
    """

    def __init__(self):
        self.level = None
        self._sent = {}

    def update(self, status, stale, now):
        if status.level == SIN_DATOS or stale:
            return None
        prev, self.level = self.level, status.level
        if prev is None or prev == status.level:
            return None
        if prev == FRENA:
            kind = "listo"
        elif status.level == FRENA:
            kind = "frena"
        elif status.level == OJO and prev == LIBRE:
            kind = "ojo"
        else:
            return None
        if now - self._sent.get(kind, float("-inf")) < COOLDOWN:
            return None
        self._sent[kind] = now
        return build_alert(kind, status)
