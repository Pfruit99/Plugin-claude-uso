"""Conteo de tokens a partir de los logs de Claude Code."""
import json
from datetime import datetime, timedelta
from pathlib import Path

LOGS_DIR = Path.home() / ".claude" / "projects"


class TokenCounter:
    """Suma tokens de los logs (input + output + cache creada).

    Lee cada log de forma incremental (desde el ultimo offset) y guarda solo
    (epoch, total) por mensaje.
    """

    def __init__(self, logs_dir=LOGS_DIR):
        self.logs_dir = Path(logs_dir)
        self._cache = {}  # path -> [offset, {clave: (epoch, total)}]

    def _scan_file(self, path, size):
        state = self._cache.get(path)
        if state is None or size < state[0]:
            state = self._cache[path] = [0, {}]
        offset, rows = state
        if size == offset:
            return rows.values()
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                data = fh.read()
        except OSError:
            return rows.values()
        end = data.rfind(b"\n") + 1  # solo lineas completas
        if end == 0:
            return rows.values()
        for line in data[:end].splitlines():
            if b'"usage"' not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            msg = obj.get("message") or {}
            usage = msg.get("usage")
            ts = obj.get("timestamp")
            if not usage or not ts or obj.get("type") != "assistant":
                continue
            try:
                epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            total = (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                     + usage.get("cache_creation_input_tokens", 0))
            key = (msg.get("id"), obj.get("requestId")) if msg.get("id") else (ts, total)
            prev = rows.get(key)
            if prev is None or total > prev[1]:
                rows[key] = (epoch, total)
        state[0] = offset + end
        return rows.values()

    def totals(self, week_start):
        """(tokens de hoy, tokens desde week_start)."""
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = (min(today_start, week_start) - timedelta(days=1)).timestamp()
        week_ts, today_ts = week_start.timestamp(), today_start.timestamp()
        today = week = 0
        seen = set()
        for path in self.logs_dir.rglob("*.jsonl"):
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_mtime < horizon:
                continue
            seen.add(path)
            for epoch, total in self._scan_file(path, st.st_size):
                if epoch >= week_ts:
                    week += total
                if epoch >= today_ts:
                    today += total
        for path in set(self._cache) - seen:  # poda de logs viejos o borrados
            del self._cache[path]
        return today, week
