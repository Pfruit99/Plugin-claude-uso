"""Registro de proveedores de limites: un agente por entrada; Claude siempre activo, el resto con `<nombre>_enabled`."""
from .base import STATE_TEXT, Reading
from .claude import ClaudeProvider
from .codex import CodexProvider

PROVIDERS = {"claude": ClaudeProvider(), "codex": CodexProvider()}


def is_enabled(cfg, name):
    return name == "claude" or bool(cfg.get(f"{name}_enabled"))


__all__ = ["PROVIDERS", "STATE_TEXT", "Reading", "is_enabled"]
