"""Codex: limites de la cuenta de ChatGPT preguntando a `codex app-server` (JSON por lineas sobre stdio).

El widget nunca lee ni guarda credenciales: usa la sesion del propio Codex. El protocolo es experimental,
asi que cualquier fallo se convierte en un Reading con estado y se registra en el log.
"""
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ..limits import Limits, Window
from .base import ERROR, NO_INSTALADO, OK, SIN_SESION, Reading

CREATE_NO_WINDOW = 0x08000000
TIMEOUT_S = 15.0
_LOGIN_HINTS = ("login", "log in", "sign in", "signin", "auth", "unauthor", "not logged", "token", "credential", "401")


class CodexError(Exception):
    def __init__(self, state, message):
        super().__init__(message)
        self.state, self.message = state, message


# --- localizar el binario -----------------------------------------------------------
def _version_key(exe):
    """Numeros de version de la carpeta de la extension (openai.chatgpt-26.1007...), para elegir la mas nueva."""
    return [int(n) for n in re.findall(r"\d+", exe.parents[2].name)]


def find_codex(configured=""):
    """Ruta de codex: la configurada, el PATH, npm global o la extension mas reciente de VS Code / Cursor."""
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which("codex")
    if found:
        return Path(found)
    npm = Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd"
    if npm.is_file():
        return npm
    home = Path.home()
    extensions = [p for base in (".vscode", ".vscode-insiders", ".cursor")
                  for p in (home / base / "extensions").glob("openai.chatgpt-*/bin/windows-*/codex.exe")]
    return max(extensions, key=_version_key) if extensions else None


# --- cliente JSON-RPC -------------------------------------------------------------
class CodexClient:
    """Lanza el servidor, pide los limites y lo termina; con tiempo maximo y sin dejar procesos huerfanos."""

    def __init__(self, command, timeout=TIMEOUT_S):
        self.command, self.timeout = list(command), timeout

    def read_rate_limits(self):
        deadline = time.monotonic() + self.timeout
        try:
            proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                                    creationflags=CREATE_NO_WINDOW)
        except FileNotFoundError:
            raise CodexError(NO_INSTALADO, "No se encontró Codex") from None
        except OSError as exc:
            raise CodexError(ERROR, f"No se pudo iniciar Codex: {exc}") from None
        lines = queue.Queue()
        threading.Thread(target=self._pump, args=(proc.stdout, lines), daemon=True).start()
        try:
            self._send(proc, {"id": 1, "method": "initialize",
                              "params": {"clientInfo": {"name": "claude-usage-widget", "version": "0.3.0"}}})
            self._wait(lines, 1, deadline)
            self._send(proc, {"method": "initialized"})
            self._send(proc, {"id": 2, "method": "account/rateLimits/read"})
            return self._wait(lines, 2, deadline)
        finally:
            self._stop(proc)

    @staticmethod
    def _pump(stream, lines):
        try:
            for line in stream:
                lines.put(line)
        except (OSError, ValueError):
            pass
        lines.put(None)  # fin del flujo

    @staticmethod
    def _send(proc, message):
        try:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            raise CodexError(ERROR, "Codex se cerró inesperadamente") from None

    @staticmethod
    def _wait(lines, msg_id, deadline):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexError(ERROR, "Codex no respondió a tiempo")
            try:
                line = lines.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            if line is None:
                raise CodexError(ERROR, "Codex se cerró inesperadamente")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("id") != msg_id or "method" in msg:
                continue  # notificaciones y peticiones del servidor: se ignoran
            if "error" in msg:
                text = str((msg["error"] or {}).get("message", msg["error"]))
                login = any(hint in text.lower() for hint in _LOGIN_HINTS)
                raise CodexError(SIN_SESION if login else ERROR, text[:200])
            return msg.get("result") or {}

    @staticmethod
    def _stop(proc):
        # Primero matar: cerrar stdout mientras otro hilo lo lee bloquea hasta que el proceso termine solo.
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logging.warning("El proceso de Codex no terminó tras kill()")
        for stream in (proc.stdin, proc.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


# --- interpretar la respuesta ------------------------------------------------------
def label_for(minutes):
    """Nombre de una ventana segun su duracion en minutos."""
    known = {300: "5 h", 10080: "Semana", 43200: "Mes"}
    if minutes in known:
        return known[minutes]
    if minutes % 1440 == 0:
        return f"{minutes // 1440} d"
    if minutes % 60 == 0:
        return f"{minutes // 60} h"
    return f"{minutes} min"


def _window(raw, now):
    if not isinstance(raw, dict) or raw.get("usedPercent") is None:
        return None
    minutes = raw.get("windowDurationMins")
    span = minutes * 60 if minutes else None
    label = label_for(minutes) if minutes else None
    resets = raw.get("resetsAt")
    if resets is not None and resets <= now:
        return Window(0.0, None, span, label)
    return Window(float(raw["usedPercent"]), resets, span, label)


def parse_rate_limits(result, now=None):
    """`result` de account/rateLimits/read -> Limits. Las ventanas se reparten por duracion: la corta a la
    ranura `five` y la larga a `week`; con una sola, va a la ranura que le corresponda por su duracion."""
    now = time.time() if now is None else now
    snapshot = result.get("rateLimits") or (result.get("rateLimitsByLimitId") or {}).get("codex") or {}
    windows = [w for w in (_window(snapshot.get("primary"), now), _window(snapshot.get("secondary"), now)) if w]
    windows.sort(key=lambda w: w.span or float("inf"))
    five = week = None
    if len(windows) == 1:
        if windows[0].span and windows[0].span <= 86400:
            five = windows[0]
        else:
            week = windows[0]
    elif len(windows) >= 2:
        five, week = windows[0], windows[1]
    return Limits(five, week, now, None)


# --- proveedor ----------------------------------------------------------------------
def start_login(configured=""):
    """Lanza `codex login` (abre el navegador). True si se pudo iniciar."""
    exe = find_codex(configured)
    if exe is None:
        return False
    try:
        subprocess.Popen([str(exe), "login"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        return True
    except OSError:
        logging.exception("No se pudo lanzar codex login")
        return False


class CodexProvider:
    name, label, poll_seconds, slow = "codex", "Codex", 300, True

    def __init__(self):
        self.path = ""
        self._last_ok = None

    def configure(self, cfg):
        self.path = cfg.get("codex_path", "")

    def read(self):
        exe = find_codex(self.path)
        if exe is None:
            return Reading(Limits(), NO_INSTALADO, "No se encontró Codex")
        try:
            limits = parse_rate_limits(CodexClient([str(exe), "app-server"]).read_rate_limits())
            self._last_ok = limits
            return Reading(limits, OK)
        except CodexError as exc:
            if exc.state == ERROR:
                logging.warning("Codex: %s", exc.message)
            kept = self._last_ok if exc.state == ERROR else None  # un fallo puntual conserva el ultimo dato
            return Reading(kept or Limits(), exc.state, exc.message)
        except Exception:
            logging.exception("Error inesperado consultando Codex")
            return Reading(self._last_ok or Limits(), ERROR, "Error inesperado")
