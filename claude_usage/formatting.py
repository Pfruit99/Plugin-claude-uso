"""Formato de duraciones, fechas relativas y cantidades."""
import time


def fmt_duration(secs):
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{max(m, 1)} min"


def fmt_remaining(window, now=None):
    if window is None:
        return "sin dato"
    if window.resets_at is None:
        return "sin iniciar"
    now = time.time() if now is None else now
    return fmt_duration(window.resets_at - now)


def fmt_ago(updated, now=None):
    if not updated:
        return "sin datos"
    secs = (time.time() if now is None else now) - updated
    if secs < 90:
        return "ahora"
    if secs < 3600:
        return f"hace {int(secs // 60)} min"
    return f"hace {int(secs // 3600)} h"


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".", ",")
    if n >= 1_000:
        return f"{round(n / 1_000)}k"
    return str(n)
