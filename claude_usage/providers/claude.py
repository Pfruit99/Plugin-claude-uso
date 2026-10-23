"""Claude Code: los limites los escribe statusline.ps1 en ~/.claude/usage_limits.json (no requiere sesion extra)."""
from ..limits import read_limits
from .base import Reading


class ClaudeProvider:
    name, label, poll_seconds, slow = "claude", "Claude", 0, False

    def configure(self, cfg):
        pass

    def read(self):
        return Reading(read_limits())
