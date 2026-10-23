"""Integracion con Windows: log, instancia unica, tema, inicio con el sistema y avisos."""
import ctypes
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

LOG_FILE = Path.home() / ".claude-usage-widget.log"
STARTUP_LNK = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/ClaudeWidget.lnk"
ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ClaudeWidget.pyw"
ICON_FILE = ROOT / "assets" / "icon.ico"

_mutex = None
_theme_cache = (0.0, "light")


def setup_logging():
    """Con pythonw no hay consola: los errores van a un archivo."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 100_000:
            LOG_FILE.unlink()
        logging.basicConfig(filename=LOG_FILE, level=logging.WARNING, encoding="utf-8",
                            format="%(asctime)s %(levelname)s %(message)s")
        sys.excepthook = lambda *exc: logging.error("Error no controlado", exc_info=exc)
    except OSError:
        pass


def single_instance():
    """True si es la unica instancia (mutex con nombre de Windows)."""
    global _mutex
    try:
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ClaudeUsageWidget")
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except (AttributeError, OSError):
        return True


def show_error(title, text):
    """Cuadro de mensaje nativo: con pythonw no hay consola donde mostrar el error."""
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except (AttributeError, OSError):
        print(f"{title}: {text}", file=sys.stderr)


def windows_theme():
    """Tema de Windows; se consulta el registro como mucho cada 30 s."""
    global _theme_cache
    now = time.time()
    if now - _theme_cache[0] >= 30:
        _theme_cache = (now, _read_windows_theme())
    return _theme_cache[1]


def _read_windows_theme():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


def startup_enabled():
    return STARTUP_LNK.exists()


def set_startup(enable):
    """Crea o borra el acceso directo de Inicio (pythonw + ClaudeWidget.pyw)."""
    if not enable:
        STARTUP_LNK.unlink(missing_ok=True)
        return
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    exe = pyw if pyw.exists() else exe
    ps = r"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK)
$s.TargetPath = $env:EXE
$s.Arguments = '"' + $env:SCRIPT + '"'
$s.WorkingDirectory = $env:DIR
$s.WindowStyle = 7
if ($env:ICON) { $s.IconLocation = $env:ICON }
$s.Save()"""
    env = {**os.environ, "LNK": str(STARTUP_LNK), "EXE": str(exe), "SCRIPT": str(LAUNCHER), "DIR": str(ROOT),
           "ICON": str(ICON_FILE) if ICON_FILE.exists() else ""}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True,
                   creationflags=0x08000000, timeout=20)


def refresh_startup():
    """Si el inicio con Windows esta activo, recrea el acceso directo para que apunte al lanzador actual."""
    if startup_enabled():
        try:
            set_startup(True)
        except Exception:
            logging.exception("No se pudo actualizar el acceso directo de inicio")
