"""Frases que acompanan al estado, sin dependencias de interfaz."""
from .formatting import fmt_duration
from .status import FRENA, LIBRE, OJO, SIN_DATOS, window_label

WORDS = {LIBRE: "Libre", OJO: "Ojo", FRENA: "Frena", SIN_DATOS: "Sin datos"}
_ADJECTIVES = {LIBRE: "normal", OJO: "alta", FRENA: "casi al límite"}


def hint(status):
    """Una frase corta bajo la palabra de estado."""
    if status.level == SIN_DATOS:
        return "Activa la línea de estado"
    if status.level == FRENA:
        if status.exhausted:
            return "Límite agotado" + (f" · vuelve en {fmt_duration(status.reset_in)}" if status.reset_in else "")
        return "Casi sin cupo"
    if status.level == OJO:
        return "Vas más rápido que el tiempo" if status.margin is not None and status.margin < 0 else "Uso alto"
    return "Vas por debajo del ritmo" if status.margin is not None else "Todo en orden"


def margin_parts(status):
    """(antes, valor destacado, despues) para el estilo Margen."""
    if status.level == SIN_DATOS:
        return "Sin datos", "--", "activa la línea de estado"
    if status.exhausted and status.reset_in is not None:
        return "Vuelve en", fmt_duration(status.reset_in), ""
    if status.level == FRENA:
        reset = f"· reinicia en {fmt_duration(status.reset_in)}" if status.reset_in is not None else ""
        return "Quedan", f"{round(100 - status.pct)} %", reset
    if status.pct < 1:  # sin uso, el "margen" seria solo el tiempo transcurrido: no dice nada
        return "Sin uso", "0 %", f"en {status.label}"
    if status.margin is None:
        return "Has usado", f"{round(status.pct)} %", f"de {status.label}"
    if status.margin >= 0:
        return "Te sobra", fmt_duration(status.margin), "de margen"
    return "Vas", fmt_duration(-status.margin), "por delante"


def pill_text(status, agent=None):
    """Texto de la capsula; `agent` nombra al agente cuando no es Claude."""
    word = WORDS[status.level]
    if status.level == SIN_DATOS:
        text = word
    elif status.level == FRENA:
        if status.exhausted and status.reset_in is not None:
            text = f"{word} · vuelve {fmt_duration(status.reset_in)}"
        else:
            text = f"{word} · {round(status.pct)} %"
    else:
        text = f"{word} · {fmt_duration(status.reset_in)}" if status.reset_in is not None else word
    return f"{text} · {agent}" if agent else text


def other_window_note(status, limits):
    """Linea sobre la ventana que no decide el estado, p. ej. 'Semana: 21 % · normal'."""
    other = {"five": "week", "week": "five"}.get(status.key)
    window = getattr(limits, other, None) if other else None
    if window is None:
        return ""
    adjective = "agotada" if window.pct >= 100 else _ADJECTIVES[status.levels[other]]
    return f"{window_label(other, window)}: {round(window.pct)} % · {adjective}"
