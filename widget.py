"""Widget de escritorio para ver el uso de Claude (limite de 5 h y semanal)."""
import ctypes
import json
import logging
import math
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
LIMITS_FILE = HOME / ".claude" / "usage_limits.json"
LOGS_DIR = HOME / ".claude" / "projects"
CONFIG_FILE = HOME / ".claude-usage-widget.json"
LOG_FILE = HOME / ".claude-usage-widget.log"

ANIM_MS = 16  # ~60 fps solo mientras un valor cambia
TOKENS_EVERY = 30
STALE_SECONDS = 15 * 60
KEY_COLOR = "#010203"
PAD = 18

THEMES = {
    "light": dict(bg="#FFFFFF", border="#D3D1C7", track="#E8E6DE", text="#2C2C2A", sub="#5F5E5A",
                  muted="#888780", banner_bg="#FCEBEB", banner_text="#A32D2D"),
    "dark": dict(bg="#1E1E1C", border="#444441", track="#33332F", text="#F1EFE8", sub="#B4B2A9",
                 muted="#888780", banner_bg="#3B1010", banner_text="#F09595"),
}
OK, WARN, BAD = "#1D9E75", "#BA7517", "#E24B4A"
ACCENT = "#D97757"

DEFAULT_CONFIG = dict(view="ring", size="full", theme="auto", topmost=True, x=None, y=None,
                      refresh=15, warn=70, bad=90, opacity=100)
RESETTABLE = ("view", "size", "theme", "topmost", "refresh", "warn", "bad", "opacity")
STARTUP_LNK = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/ClaudeWidget.lnk"
THEME_CHOICES = (("Seguir a Windows", "auto"), ("Claro", "light"), ("Oscuro", "dark"))
REFRESH_CHOICES = (("5 s", 5), ("15 s", 15), ("30 s", 30), ("60 s", 60))


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


def enable_dpi_awareness():
    """Texto nitido en pantallas con escala > 100 %."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def single_instance():
    """True si es la unica instancia (mutex con nombre de Windows)."""
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "ClaudeUsageWidget")
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except (AttributeError, OSError):
        return True


def _int_in(value, lo, hi, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(max(lo, min(hi, value)))


def sanitize_config(cfg):
    """Valida rangos y tipos; lo invalido vuelve al valor por defecto."""
    d = DEFAULT_CONFIG
    if cfg.get("view") not in ("ring", "bar"):
        cfg["view"] = d["view"]
    if cfg.get("size") not in ("compact", "full"):
        cfg["size"] = d["size"]
    if cfg.get("theme") not in {v for _, v in THEME_CHOICES}:
        cfg["theme"] = d["theme"]
    cfg["topmost"] = bool(cfg.get("topmost", d["topmost"]))
    cfg["refresh"] = _int_in(cfg.get("refresh"), 5, 300, d["refresh"])
    cfg["opacity"] = _int_in(cfg.get("opacity"), 30, 100, d["opacity"])
    cfg["warn"] = _int_in(cfg.get("warn"), 1, 98, d["warn"])
    cfg["bad"] = _int_in(cfg.get("bad"), cfg["warn"] + 1, 100, max(d["bad"], cfg["warn"] + 1))
    return cfg


def load_config():
    try:
        data = json.loads(CONFIG_FILE.read_text("utf-8-sig"))
        return sanitize_config({**DEFAULT_CONFIG, **(data if isinstance(data, dict) else {})})
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)


def startup_enabled():
    return STARTUP_LNK.exists()


def set_startup(enable):
    """Crea o borra el acceso directo de Inicio (pythonw + widget.pyw)."""
    import subprocess
    if not enable:
        STARTUP_LNK.unlink(missing_ok=True)
        return
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    exe = pyw if pyw.exists() else exe
    here = Path(__file__).resolve().parent
    ps = r"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK)
$s.TargetPath = $env:EXE
$s.Arguments = '"' + $env:SCRIPT + '"'
$s.WorkingDirectory = $env:DIR
$s.WindowStyle = 7
if ($env:ICON) { $s.IconLocation = $env:ICON }
$s.Save()"""
    icon = here / "assets" / "icon.ico"
    env = {**os.environ, "LNK": str(STARTUP_LNK), "EXE": str(exe),
           "SCRIPT": str(here / "widget.pyw"), "DIR": str(here), "ICON": str(icon) if icon.exists() else ""}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True,
                   creationflags=0x08000000, timeout=20)


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg), "utf-8")
    except OSError:
        pass


_theme_cache = (0.0, "light")


def windows_theme():
    """Tema de Windows; se consulta el registro como mucho cada 30 s."""
    global _theme_cache
    now = time.time()
    if now - _theme_cache[0] < 30:
        return _theme_cache[1]
    _theme_cache = (now, _read_windows_theme())
    return _theme_cache[1]


def _read_windows_theme():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


def level_color(pct, warn=70, bad=90):
    if pct is None:
        return "#B4B2A9"
    return BAD if pct >= bad else WARN if pct >= warn else OK


def fmt_duration(secs):
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{max(m, 1)} min"


def fmt_remaining(window):
    if window is None:
        return "sin dato"
    if window[1] is None:
        return "sin iniciar"
    return fmt_duration(window[1] - time.time())


def fmt_ago(updated):
    if not updated:
        return "sin datos"
    secs = time.time() - updated
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


def read_limits():
    """Devuelve (five_hour, seven_day, updated, context); ventana = (pct, resets_at) o None."""
    try:
        data = json.loads(LIMITS_FILE.read_text("utf-8-sig"))
    except (OSError, ValueError):
        return None, None, None, None

    def window(key):
        w = data.get(key) or {}
        pct = w.get("used_percentage")
        if pct is None:
            return None
        resets = w.get("resets_at")
        if resets is not None and resets <= time.time():
            return 0.0, None
        return float(pct), resets

    return window("five_hour"), window("seven_day"), data.get("updated"), data.get("context")


class TokenCounter:
    """Suma tokens de los logs de Claude Code (input + output + cache creada).

    Lee cada log de forma incremental (desde el ultimo offset) y guarda solo
    (epoch, total) por mensaje.
    """

    def __init__(self):
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
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = (min(today_start, week_start) - timedelta(days=1)).timestamp()
        week_ts, today_ts = week_start.timestamp(), today_start.timestamp()
        today = week = 0
        seen = set()
        for path in LOGS_DIR.rglob("*.jsonl"):
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


def rounded_pts(x1, y1, x2, y2, r):
    """Puntos de un rectangulo redondeado para create_polygon(smooth=True)."""
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
            x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


class MenuPanel:
    """Panel flotante de opciones: selectores con icono y acciones, con la paleta del widget."""

    W, SEG_H, ACT_H, PADX = 236, 40, 34, 14

    def __init__(self, app, x, y):
        self.app, self.S = app, app.S
        self.hover = None
        self.regions = []  # (x1, y1, x2, y2, accion) en coordenadas logicas
        win = self.win = tk.Toplevel(app.root)
        win.overrideredirect(True)
        win.configure(bg=KEY_COLOR)
        win.attributes("-transparentcolor", KEY_COLOR)
        win.attributes("-topmost", True)
        win.attributes("-alpha", app.cfg["opacity"] / 100)
        self.c = tk.Canvas(win, bg=KEY_COLOR, highlightthickness=0)
        self.c.pack()
        self.draw()
        win.update_idletasks()
        x = max(0, min(x, win.winfo_screenwidth() - self.c.winfo_reqwidth() - 8))
        y = max(0, min(y, win.winfo_screenheight() - self.c.winfo_reqheight() - 8))
        win.geometry(f"+{x}+{y}")
        self.c.bind("<Motion>", self._motion)
        self.c.bind("<Leave>", lambda e: self._set_hover(None))
        self.c.bind("<ButtonRelease-1>", self._click)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<Key-r>", lambda e: self._run(("act", "refresh")))
        win.bind("<FocusOut>", lambda e: win.after(80, self._check_focus))
        win.focus_force()

    def alive(self):
        return self.win.winfo_exists()

    def close(self):
        if self.alive():
            self.win.destroy()
        self.app._panel = None

    def _check_focus(self):
        if self.alive() and self.win.focus_displayof() is None:
            self.close()

    def _hit(self, e):
        x, y = e.x / self.S, e.y / self.S
        for x1, y1, x2, y2, action in self.regions:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return action
        return None

    def _motion(self, e):
        self._set_hover(self._hit(e))

    def _set_hover(self, action):
        if action != self.hover:
            self.hover = action
            self.draw()

    def _click(self, e):
        action = self._hit(e)
        if action:
            self._run(action)

    def _run(self, action):
        app, kind = self.app, action[0]
        if kind == "set":
            {"view": app.set_view, "size": app.set_size, "theme": app.set_theme}[action[1]](action[2])
            self.draw()
            return
        self.close()
        {"settings": app.open_settings, "exit": app.root.destroy,
         "refresh": lambda: app.refresh(reschedule=False)}[action[1]]()

    # --- dibujo -----------------------------------------------------------------
    def _icon(self, kind, cx, cy, color):
        c, S = self.c, self.S
        if kind == "ring":
            c.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=color, width=S * 1.2)
            c.create_arc(cx - 7, cy - 7, cx + 7, cy + 7, start=90, extent=-250, style="arc",
                         outline=color, width=S * 3.2)
        elif kind == "bar":
            c.create_rectangle(cx - 8, cy - 3, cx + 8, cy + 3, outline=color, width=S * 1.2)
            c.create_rectangle(cx - 8, cy - 3, cx + 2, cy + 3, fill=color, outline=color)
        elif kind == "compact":
            c.create_rectangle(cx - 8, cy - 4, cx + 8, cy + 4, outline=color, width=S * 1.6)
        elif kind == "full":
            c.create_rectangle(cx - 7, cy - 9, cx + 7, cy + 9, outline=color, width=S * 1.6)
            c.create_line(cx - 7, cy - 3, cx + 7, cy - 3, fill=color, width=S * 1.2)
        else:
            c.create_text(cx, cy, text=kind, fill=color, font=("Segoe UI Symbol", 13))

    def draw(self):
        app, c, S = self.app, self.c, self.S
        p, cfg = app.palette(), app.cfg
        c.delete("all")
        self.regions = []
        segs = (
            ("Vista", "view", (("ring", "ring"), ("bar", "bar"))),
            ("Tamaño", "size", (("compact", "compact"), ("full", "full"))),
            ("Tema", "theme", (("auto", "A"), ("light", "☀"), ("dark", "☾"))),
        )
        y = 10
        for label, key, options in segs:
            c.create_text(self.PADX + 2, y + self.SEG_H / 2, text=label, anchor="w", fill=p["text"],
                          font=("Segoe UI", 10))
            x2 = self.W - self.PADX
            for value, icon in reversed(options):
                x1, y1, y2 = x2 - 36, y + 6, y + self.SEG_H - 6
                action = ("set", key, value)
                active = cfg[key] == value
                fill = ACCENT if active else (p["border"] if self.hover == action else p["track"])
                c.create_polygon(rounded_pts(x1, y1, x2, y2, 7), smooth=True, fill=fill, outline=fill)
                self._icon(icon, (x1 + x2) / 2, (y1 + y2) / 2, "#FFFFFF" if active else p["sub"])
                self.regions.append((x1, y1, x2, y2, action))
                x2 = x1 - 4
            y += self.SEG_H
        y += 4
        c.create_line(self.PADX, y, self.W - self.PADX, y, fill=p["border"])
        y += 6
        for glyph, label, name, color, hint in (
            ("⚙", "Ajustes…", "settings", p["text"], ""),
            ("↻", "Actualizar ahora", "refresh", p["text"], "R"),
            ("✕", "Salir", "exit", BAD, ""),
        ):
            action = ("act", name)
            x1, x2, y1, y2 = 6, self.W - 6, y, y + self.ACT_H
            if self.hover == action:
                c.create_polygon(rounded_pts(x1, y1, x2, y2, 7), smooth=True, fill=p["track"], outline=p["track"])
            c.create_text(self.PADX + 8, (y1 + y2) / 2, text=glyph, fill=color, font=("Segoe UI Symbol", 12))
            c.create_text(self.PADX + 30, (y1 + y2) / 2, text=label, anchor="w", fill=color, font=("Segoe UI", 10))
            if hint:
                c.create_text(self.W - self.PADX - 4, (y1 + y2) / 2, text=hint, anchor="e", fill=p["muted"],
                              font=("Segoe UI", 9))
            self.regions.append((x1, y1, x2, y2, action))
            y += self.ACT_H
        height = y + 8
        c.create_polygon(rounded_pts(0.5, 0.5, self.W - 0.5, height - 0.5, 14), smooth=True, tags="bg",
                         fill=p["bg"], outline=p["border"])
        c.tag_lower("bg")
        c.scale("all", 0, 0, S, S)
        c.config(width=round(self.W * S), height=round(height * S))


class Widget:
    WIDTHS = {"compact": 290, "full": 330}

    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("Uso de Claude")
        self.root.overrideredirect(True)
        self.root.configure(bg=KEY_COLOR)
        self.root.attributes("-transparentcolor", KEY_COLOR)
        self.root.attributes("-topmost", self.cfg["topmost"])
        self.root.attributes("-alpha", self.cfg["opacity"] / 100)
        self.root.report_callback_exception = lambda *exc: logging.error("Error en Tk", exc_info=exc)
        self.S = self.root.winfo_fpixels("1i") / 96  # factor de escala de pantalla
        self.canvas = tk.Canvas(self.root, width=int(330 * self.S), height=int(260 * self.S),
                                bg=KEY_COLOR, highlightthickness=0)
        self.canvas.pack()
        self.counter = TokenCounter()
        self.tokens = (0, 0)
        self.limits = (None, None, None, None)
        self._busy = False
        self._sig = None
        self._shown = {}  # porcentaje mostrado (animado) por ventana
        self._anim_job = None
        self._tokens_at = 0.0
        self._refresh_job = None
        self._hover = False
        self._settings = None
        self._panel = None
        self._svars = {}
        self._drag = (0, 0)
        self._moved = False
        self._menu = self._build_menu()
        self.W = self.WIDTHS[self.cfg["size"]]
        c = self.canvas
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Double-Button-1>", lambda e: self.set_size("full" if self.cfg["size"] == "compact" else "compact"))
        c.bind("<Button-3>", self._popup)
        c.bind("<Enter>", lambda e: self._set_hover(True))
        c.bind("<Leave>", lambda e: self._set_hover(False))
        self.refresh()

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        self.var_view = tk.StringVar(value=self.cfg["view"])
        self.var_size = tk.StringVar(value=self.cfg["size"])
        self.var_theme = tk.StringVar(value=self.cfg["theme"])
        self.var_top = tk.BooleanVar(value=self.cfg["topmost"])
        for title, var, options, command in (
            ("Vista", self.var_view, (("Anillos de progreso", "ring"), ("Barras de porcentaje", "bar")), self.set_view),
            ("Tamaño", self.var_size, (("Compacto", "compact"), ("Completo", "full")), self.set_size),
            ("Tema", self.var_theme, THEME_CHOICES, self.set_theme),
        ):
            sub = tk.Menu(m, tearoff=0)
            for label, value in options:
                sub.add_radiobutton(label=label, variable=var, value=value, command=lambda v=value, f=command: f(v))
            m.add_cascade(label=title, menu=sub)
        m.add_checkbutton(label="Siempre encima", variable=self.var_top, command=self.toggle_top)
        m.add_separator()
        m.add_command(label="Ajustes…", command=self.open_settings)
        m.add_command(label="Actualizar ahora", command=lambda: self.refresh(reschedule=False))
        m.add_command(label="Salir", command=self.root.destroy)
        return m

    def _popup(self, event):
        """Panel grafico; si falla, cae al menu nativo."""
        if self._panel is not None and self._panel.alive():
            self._panel.close()
            return
        try:
            self._panel = MenuPanel(self, event.x_root, event.y_root)
        except Exception:
            logging.exception("No se pudo abrir el panel")
            self._panel = None
            self._menu.tk_popup(event.x_root, event.y_root)

    def _press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._start = (e.x_root, e.y_root)
        self._moved = False

    def _motion(self, e):
        if abs(e.x_root - self._start[0]) + abs(e.y_root - self._start[1]) > 3:
            self._moved = True
        if self._moved:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        if self._moved:
            self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
            save_config(self.cfg)
        elif e.y < 40 * self.S:
            S = self.S
            if self.cfg["size"] == "compact" and e.x > (self.W - 44) * S:
                self._popup(e)
            elif self.cfg["size"] == "full" and (PAD + 104) * S < e.x < (PAD + 134) * S:
                self._popup(e)
            elif self.cfg["size"] == "full" and e.x > (self.W - 150) * S:
                self.refresh(reschedule=False)

    def set_view(self, view):
        self.cfg["view"] = view
        self.var_view.set(view)
        save_config(self.cfg)
        self.draw()

    def set_size(self, size):
        self.cfg["size"] = size
        self.var_size.set(size)
        self.W = self.WIDTHS[size]
        save_config(self.cfg)
        self.draw()

    def set_theme(self, theme):
        self.cfg["theme"] = theme
        save_config(self.cfg)
        self.draw()

    def toggle_top(self):
        self.cfg["topmost"] = self.var_top.get()
        self.root.attributes("-topmost", self.cfg["topmost"])
        save_config(self.cfg)

    def _set_hover(self, hover):
        self._hover = hover
        self.draw()

    def apply(self, key, value):
        """Aplica una opcion en vivo, la valida y la guarda."""
        cfg = self.cfg
        cfg[key] = value
        sanitize_config(cfg)
        if key == "opacity":
            self.root.attributes("-alpha", cfg["opacity"] / 100)
        elif key == "refresh":
            self._schedule_refresh()
        elif key == "size":
            self.W = self.WIDTHS[cfg["size"]]
        elif key == "topmost":
            self.root.attributes("-topmost", cfg["topmost"])
        save_config(cfg)
        self._sync_vars()
        self.draw()

    def reset(self):
        for key in RESETTABLE:
            self.cfg[key] = DEFAULT_CONFIG[key]
        self.apply("opacity", DEFAULT_CONFIG["opacity"])
        self.apply("refresh", DEFAULT_CONFIG["refresh"])
        self.apply("size", DEFAULT_CONFIG["size"])
        self.apply("topmost", DEFAULT_CONFIG["topmost"])

    def _sync_vars(self):
        """Mantiene menu y ventana de ajustes al dia con la config."""
        for var, key in ((self.var_view, "view"), (self.var_size, "size"),
                         (self.var_theme, "theme"), (self.var_top, "topmost")):
            if var.get() != self.cfg[key]:
                var.set(self.cfg[key])
        for key, var in self._svars.items():
            value = startup_enabled() if key == "startup" else self.cfg[key]
            if key == "theme":
                value = dict((v, l) for l, v in THEME_CHOICES)[value]
            elif key == "refresh":
                value = dict((v, l) for l, v in REFRESH_CHOICES)[value]
            if var.get() != value:
                var.set(value)

    def open_settings(self):
        from tkinter import ttk
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.lift()
            return
        win = self._settings = tk.Toplevel(self.root)
        win.title("Ajustes")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.bind("<Escape>", lambda e: win.destroy())
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Destroy>", lambda e: self._svars.clear() if e.widget is win else None)
        frame = ttk.Frame(win, padding=14)
        frame.pack()
        labels_theme = dict((v, l) for l, v in THEME_CHOICES)
        labels_refresh = dict((v, l) for l, v in REFRESH_CHOICES)
        self._svars = {
            "theme": tk.StringVar(value=labels_theme[self.cfg["theme"]]),
            "opacity": tk.IntVar(value=self.cfg["opacity"]),
            "refresh": tk.StringVar(value=labels_refresh[self.cfg["refresh"]]),
            "warn": tk.IntVar(value=self.cfg["warn"]),
            "bad": tk.IntVar(value=self.cfg["bad"]),
            "startup": tk.BooleanVar(value=startup_enabled()),
        }
        v = self._svars

        def section(row, title):
            ttk.Label(frame, text=title, font=("Segoe UI Semibold", 10)).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(10 if row else 0, 4))

        def row_label(row, text):
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", padx=(8, 12), pady=3)

        section(0, "Apariencia")
        row_label(1, "Tema")
        theme = ttk.Combobox(frame, textvariable=v["theme"], state="readonly", width=18,
                             values=[l for l, _ in THEME_CHOICES])
        theme.grid(row=1, column=1, columnspan=2, sticky="e")
        theme.bind("<<ComboboxSelected>>", lambda e: self.apply("theme", dict(THEME_CHOICES)[v["theme"].get()]))
        row_label(2, "Opacidad")
        ttk.Scale(frame, from_=30, to=100, length=130, value=self.cfg["opacity"],
                  command=lambda x: self.apply("opacity", round(float(x)))).grid(row=2, column=1, sticky="e")
        ttk.Label(frame, textvariable=v["opacity"], width=4).grid(row=2, column=2, sticky="e")

        section(3, "Datos")
        row_label(4, "Actualizar cada")
        refresh = ttk.Combobox(frame, textvariable=v["refresh"], state="readonly", width=18,
                               values=[l for l, _ in REFRESH_CHOICES])
        refresh.grid(row=4, column=1, columnspan=2, sticky="e")
        refresh.bind("<<ComboboxSelected>>",
                     lambda e: self.apply("refresh", dict(REFRESH_CHOICES)[v["refresh"].get()]))
        for r, key, text, lo, hi in ((5, "warn", "Aviso amarillo desde (%)", 1, 98),
                                     (6, "bad", "Aviso rojo desde (%)", 2, 100)):
            row_label(r, text)
            ttk.Spinbox(frame, from_=lo, to=hi, width=6, textvariable=v[key],
                        command=lambda k=key: self._apply_int(k)).grid(row=r, column=1, columnspan=2, sticky="e")

        section(7, "Sistema")
        ttk.Checkbutton(frame, text="Iniciar con Windows", variable=v["startup"],
                        command=self._toggle_startup).grid(row=8, column=0, columnspan=3, sticky="w", padx=8)

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Restablecer", command=self.reset).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cerrar", command=win.destroy).pack(side="left")

        win.update_idletasks()
        x = min(max(0, self.root.winfo_x()), self.root.winfo_screenwidth() - win.winfo_width() - 10)
        win.geometry(f"+{x}+{self.root.winfo_y() + self.root.winfo_height() + 8}")

    def _apply_int(self, key):
        try:
            self.apply(key, int(self._svars[key].get()))
        except (tk.TclError, ValueError):
            self._sync_vars()

    def _toggle_startup(self):
        try:
            set_startup(self._svars["startup"].get())
        except Exception:
            logging.exception("No se pudo cambiar el inicio con Windows")
        self._svars["startup"].set(startup_enabled())

    def refresh(self, reschedule=True):
        self.limits = read_limits()
        self.draw()
        if not self._busy and time.time() - self._tokens_at >= max(TOKENS_EVERY, self.cfg["refresh"]):
            self._busy = True
            self._tokens_at = time.time()
            threading.Thread(target=self._count_tokens, daemon=True).start()
        if reschedule:
            self._schedule_refresh()

    def _schedule_refresh(self):
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(self.cfg["refresh"] * 1000, self.refresh)

    def _count_tokens(self):
        try:
            week = self.limits[1]
            if week and week[1]:
                week_start = datetime.fromtimestamp(week[1] - 7 * 86400).astimezone()
            else:
                week_start = datetime.now().astimezone() - timedelta(days=7)
            self.tokens = self.counter.totals(week_start)
        finally:
            self._busy = False
        try:
            self.root.after(0, self.draw)
        except (tk.TclError, RuntimeError):
            pass

    def palette(self):
        theme = self.cfg["theme"]
        return THEMES[windows_theme() if theme == "auto" else theme]

    def _kick_anim(self):
        """Programa la animacion si el porcentaje mostrado no alcanzo al real."""
        if self._anim_job is not None:
            return
        for key, window in (("five", self.limits[0]), ("week", self.limits[1])):
            target = window[0] if window else None
            if target is None:
                self._shown[key] = None
                continue
            if self._shown.get(key) is None:
                self._shown[key] = 0.0
            if self._shown[key] != target:
                self._anim_job = self.root.after(ANIM_MS, self._animate)
                return

    def _animate(self):
        self._anim_job = None
        for key, window in (("five", self.limits[0]), ("week", self.limits[1])):
            target = window[0] if window else None
            shown = self._shown.get(key)
            if target is None or shown is None:
                continue
            self._shown[key] = target if abs(target - shown) < 0.3 else shown + (target - shown) * 0.22
        self.draw()  # vuelve a programar la animacion si falta recorrido

    def _shown_window(self, key, window):
        if window is None or self._shown.get(key) is None:
            return window
        return self._shown[key], window[1]

    def draw(self):
        c, p, W, S = self.canvas, self.palette(), self.W, self.S
        self._kick_anim()
        five, week = self._shown_window("five", self.limits[0]), self._shown_window("week", self.limits[1])
        updated, context = self.limits[2], self.limits[3]
        full = self.cfg["size"] == "full"
        ring = self.cfg["view"] == "ring"
        stale = bool(updated) and time.time() - updated > STALE_SECONDS
        exhausted = any(w and w[0] >= 100 for w in (five, week))
        sig = (five, week, updated, context, self.tokens, tuple(self.cfg.values()), p["bg"], W,
               int(time.time() // 60), self._hover)
        if sig == self._sig:
            return
        self._sig = sig
        c.delete("all")

        c.create_text(PAD, 24, text="Uso de Claude" if full else "Claude", anchor="w",
                      fill=p["text"], font=("Segoe UI Semibold", 12 if full else 11))
        if full:
            c.create_text(W - PAD, 24, anchor="e", fill=WARN if stale or not updated else p["muted"],
                          font=("Segoe UI", 9), text=f"↻ {fmt_ago(updated)}")
            if self._hover:
                c.create_text(PAD + 118, 24, text="⚙", fill=p["muted"], font=("Segoe UI Symbol", 13))
        else:
            c.create_text(W - PAD, 24, text="⚙", anchor="e", fill=p["muted"], font=("Segoe UI Symbol", 14))

        y = 44
        if exhausted:
            both = five and week and five[0] >= 100 and week[0] >= 100
            msg = ("Límites de 5 h y semanal agotados" if both
                   else "Límite de 5 h agotado" if five and five[0] >= 100 else "Límite semanal agotado")
            self._rounded(PAD, y, W - PAD, y + 28, 8, fill=p["banner_bg"], outline=p["banner_bg"])
            c.create_text(PAD + 10, y + 14, text=f"⚠  {msg}", anchor="w", fill=p["banner_text"], font=("Segoe UI", 9))
            y += 38
        if five is None and week is None:
            c.create_text(PAD, y + 4, anchor="w", fill=WARN, font=("Segoe UI", 8),
                          text="Sin datos de límites: activa la línea de estado")
            y += 20

        if ring:
            y = self._rings(y, five, week, p, full)
        else:
            y = self._bars(y, five, week, p, full)

        if full:
            c.create_line(PAD, y + 4, W - PAD, y + 4, fill=p["border"])
            today, wk = self.tokens
            stats = (("Hoy", fmt_tokens(today)), ("Semana", fmt_tokens(wk)),
                     ("Contexto", "--" if context is None else f"{round(context)}%"))
            inner = W - 2 * PAD
            for i, (label, value) in enumerate(stats):
                x = PAD + inner * (2 * i + 1) / 6
                c.create_text(x, y + 22, text=label, fill=p["muted"], font=("Segoe UI", 9))
                c.create_text(x, y + 42, text=value, fill=p["text"], font=("Segoe UI Semibold", 13))
            y += 60
        height = y + 8
        self._rounded(0.5, 0.5, W - 0.5, height - 0.5, 18, tags="bg", fill=p["bg"],
                      outline=BAD if exhausted else p["border"])
        c.tag_lower("bg")
        c.scale("all", 0, 0, S, S)  # el dibujo es logico (96 dpi); aqui se pasa a pixeles reales
        c.config(width=round(W * S), height=round(height * S))

    def _rounded(self, x1, y1, x2, y2, r, tags=(), **kw):
        self.canvas.create_polygon(rounded_pts(x1, y1, x2, y2, r), smooth=True, width=1, tags=tags, **kw)

    def _bars(self, y, five, week, p, full):
        W = self.W
        if full:
            self._bar_full(y + 12, "Ventana de 5 horas", five, p)
            self._bar_full(y + 82, "Semanal", week, p)
            return y + 134
        self._bar_compact(y + 16, "5 horas", five, p)
        self._bar_compact(y + 62, "Semana", week, p)
        return y + 90

    def _bar_full(self, y, label, window, p):
        c, w = self.canvas, self.W - 2 * PAD
        pct = window[0] if window else None
        full = pct is not None and pct >= 100
        c.create_text(PAD, y, text=label, anchor="w", fill=p["text"], font=("Segoe UI", 11))
        c.create_text(PAD + w, y, text="--" if pct is None else f"{round(pct)}%", anchor="e",
                      fill=BAD if full else p["sub"], font=("Segoe UI Semibold", 11))
        self._track(PAD, y + 14, w, 8, pct, p)
        text = f"Vuelve en {fmt_remaining(window)}" if full else f"Se reinicia en {fmt_remaining(window)}"
        c.create_text(PAD, y + 38, text=text, anchor="w", fill=BAD if full else p["muted"], font=("Segoe UI", 9))

    def _bar_compact(self, y, label, window, p):
        c, w = self.canvas, self.W - 2 * PAD
        pct = window[0] if window else None
        full = pct is not None and pct >= 100
        rem = fmt_remaining(window)
        right = "--" if pct is None else (f"100% · vuelve en {rem}" if full else f"{round(pct)}% · {rem}")
        c.create_text(PAD, y, text=label, anchor="w", fill=p["text"], font=("Segoe UI", 10))
        c.create_text(PAD + w, y, text=right, anchor="e", fill=BAD if full else p["sub"], font=("Segoe UI", 9))
        self._track(PAD, y + 12, w, 6, pct, p)

    def _track(self, x, y, w, h, pct, p):
        self._pill(x, y, x + w, y + h, p["track"])
        if pct:
            self._pill(x, y, x + max(h, w * min(pct, 100) / 100), y + h, level_color(pct, self.cfg["warn"], self.cfg["bad"]))

    def _pill(self, x1, y1, x2, y2, color):
        r = (y2 - y1) / 2
        c = self.canvas
        c.create_oval(x1, y1, x1 + 2 * r, y2, fill=color, outline=color)
        c.create_oval(x2 - 2 * r, y1, x2, y2, fill=color, outline=color)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)

    def _rings(self, y, five, week, p, full):
        W = self.W
        r, w = (44, 10) if full else (32, 8)
        cy = y + (22 + r + 12 if full else 18 + r + 8)
        for cx, label, window in ((W * 0.25, "5 h", five), (W * 0.75, "Semana", week)):
            self._ring(cx, cy, r, w, label, window, p, full)
        return cy + r + (28 if full else 24)

    def _ring(self, cx, cy, r, w, label, window, p, full):
        c = self.canvas
        pct = window[0] if window else None
        done = pct is not None and pct >= 100
        color = level_color(pct, self.cfg["warn"], self.cfg["bad"])
        c.create_text(cx, cy - r - w / 2 - 10, text=label, fill=p["sub"], font=("Segoe UI", 10 if full else 9))
        sw = w * self.S  # el grosor de linea no se escala con canvas.scale
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=p["track"], width=sw)
        if done:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=sw)
        elif pct:
            extent = -pct * 3.6
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=extent, style="arc", outline=color, width=sw)
            for ang in (90, 90 + extent):
                x = cx + r * math.cos(math.radians(ang))
                y = cy - r * math.sin(math.radians(ang))
                c.create_oval(x - w / 2, y - w / 2, x + w / 2, y + w / 2, fill=color, outline=color)
        c.create_text(cx, cy, text="--" if pct is None else f"{round(pct)}%", fill=BAD if done else p["text"],
                      font=("Segoe UI Semibold", 17 if full else 13))
        rem = fmt_remaining(window)
        c.create_text(cx, cy + r + w / 2 + 14, text=f"vuelve en {rem}" if done else rem,
                      fill=BAD if done else p["sub"], font=("Segoe UI", 9))

    def run(self):
        self.root.update_idletasks()
        x, y = self.cfg["x"], self.cfg["y"]
        if x is None or y is None:
            x = self.root.winfo_screenwidth() - round((self.W + 24) * self.S)
            y = round(24 * self.S)
        # que no quede fuera de pantalla si cambio el monitor
        x = max(0, min(x, self.root.winfo_screenwidth() - 60))
        y = max(0, min(y, self.root.winfo_screenheight() - 60))
        self.root.geometry(f"+{x}+{y}")
        self.root.mainloop()


def main():
    setup_logging()
    if not single_instance():
        return
    enable_dpi_awareness()
    Widget().run()


if __name__ == "__main__":
    main()
