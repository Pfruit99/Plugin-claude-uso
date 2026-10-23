"""Ventana flotante: reune datos, animacion y eventos; el dibujo lo hace el estilo elegido."""
import logging
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from .. import APP_NAME, config, winsys
from ..limits import Limits, Window, read_limits
from ..status import compute_status
from ..texts import WINDOW_NAMES, WORDS
from ..tokens import TokenCounter
from .fonts import Fonts
from .icon import make_icon
from .panel import Panel
from .settings import SettingsDialog
from .styles import STYLES
from .styles.base import Context
from .theme import THEMES, M

ANIM_MS = 16        # ~60 fps solo mientras un valor cambia
TOKENS_EVERY = 30
HOVER_LEAVE_MS = 250  # retardo al salir el raton, para que la pildora no parpadee


class Bridge(QObject):
    tokens_ready = Signal()


class Card(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.cfg = config.load_config()
        self.fonts = Fonts()
        self.counter = TokenCounter()
        self.tokens = (0, 0)
        self.limits = Limits()
        self.bridge = Bridge()
        self.bridge.tokens_ready.connect(self.relayout)
        self._busy = False
        self._tokens_at = 0.0
        self._shown = {}
        self._panel = self._settings = self.tray = None
        self._hover = False
        self._press = self._origin = None
        self._moved = False
        self._layout = None

        self.anim = QTimer(self)
        self.anim.setInterval(ANIM_MS)
        self.anim.timeout.connect(self._animate)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.minute = QTimer(self)  # actualiza las cuentas atras y el estado por ritmo
        self.minute.setInterval(30_000)
        self.minute.timeout.connect(self.relayout)
        self.minute.start()
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.setInterval(HOVER_LEAVE_MS)
        self.leave_timer.timeout.connect(self._end_hover)
        self.save_timer = QTimer(self)  # agrupa guardados seguidos (p. ej. al mover el deslizador)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(lambda: config.save_config(self.cfg))

        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.cfg["topmost"])
        self.setWindowOpacity(self.cfg["opacity"] / 100)
        self.refresh()

    # --- configuracion ----------------------------------------------------------
    def palette_(self):
        theme = self.cfg["theme"]
        return THEMES[winsys.windows_theme() if theme == "auto" else theme]

    def save(self):
        self.save_timer.start()

    def flush_save(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            config.save_config(self.cfg)

    def _set(self, key, value):
        self.cfg[key] = value
        self.save()
        self.relayout()

    def set_style(self, v):
        self._set("style", v)

    def set_view(self, v):
        self._set("view", v)

    def set_size(self, v):
        self._set("size", v)

    def set_theme(self, v):
        self._set("theme", v)

    def apply(self, key, value):
        cfg = self.cfg
        cfg[key] = value
        config.sanitize_config(cfg)
        if key == "opacity":
            self.setWindowOpacity(cfg["opacity"] / 100)
        elif key == "refresh":
            self._schedule()
        elif key == "topmost":
            self.setWindowFlag(Qt.WindowStaysOnTopHint, cfg["topmost"])
            self.show()
        self.save()
        self.relayout()

    def reset(self):
        for key in config.RESETTABLE:
            self.apply(key, config.DEFAULT_CONFIG[key])

    def open_settings(self):
        if self._settings is not None and self._settings.isVisible():
            self._settings.raise_()
            return
        self._settings = SettingsDialog(self)
        self._settings.setAttribute(Qt.WA_DeleteOnClose)
        self._settings.show()
        self._settings.move(self.x(), self.y() + self.height() + 8)

    # --- datos ------------------------------------------------------------------
    def refresh(self, reschedule=True):
        self.limits = read_limits()
        self.relayout()
        if not self._busy and time.time() - self._tokens_at >= max(TOKENS_EVERY, self.cfg["refresh"]):
            self._busy = True
            self._tokens_at = time.time()
            threading.Thread(target=self._count_tokens, daemon=True).start()
        if reschedule:
            self._schedule()

    def _schedule(self):
        self.timer.start(self.cfg["refresh"] * 1000)

    def _count_tokens(self):
        try:
            week = self.limits.week
            if week and week.resets_at:
                week_start = datetime.fromtimestamp(week.resets_at - 7 * 86400).astimezone()
            else:
                week_start = datetime.now().astimezone() - timedelta(days=7)
            self.tokens = self.counter.totals(week_start)
        except Exception:
            logging.exception("Error contando tokens")
        finally:
            self._busy = False
        self.bridge.tokens_ready.emit()

    def tooltip(self):
        st = compute_status(self.limits, self.cfg["warn"], self.cfg["bad"])

        def part(key, window):
            return f"{WINDOW_NAMES[key]} {round(window.pct)}%" if window else f"{WINDOW_NAMES[key]} --"
        return f"{APP_NAME}\n{WORDS[st.level]} · {part('five', self.limits.five)} · {part('week', self.limits.week)}"

    # --- contexto, tamano y animacion -------------------------------------------
    def _animated(self, key, window):
        shown = self._shown.get(key)
        return window if window is None or shown is None else Window(shown, window.resets_at)

    def _context(self):
        now = time.time()
        cfg = self.cfg
        animated = replace(self.limits, five=self._animated("five", self.limits.five),
                           week=self._animated("week", self.limits.week))
        return Context(limits=animated, real=self.limits, status=compute_status(self.limits, cfg["warn"], cfg["bad"], now),
                       tokens=self.tokens, cfg=cfg, pal=self.palette_(), fonts=self.fonts, hover=self._hover, now=now)

    def _style_layout(self):
        ctx = self._context()
        style = STYLES[self.cfg["style"]]
        return ctx, style, style.layout(ctx)

    def relayout(self):
        if self.tray is not None:
            self.tray.setToolTip(self.tooltip())
        _, _, layout = self._style_layout()
        self._layout = layout
        self.setFixedSize(layout.w + 2 * M, layout.h + 2 * M)
        self._kick_anim()
        self.update()

    def _kick_anim(self):
        for key, window in (("five", self.limits.five), ("week", self.limits.week)):
            if window is None:
                self._shown[key] = None
            elif self._shown.get(key) is None:
                self._shown[key] = 0.0
        if not self.anim.isActive() and self._anim_pending():
            self.anim.start()

    def _anim_pending(self):
        return any(w is not None and self._shown.get(k) != w.pct
                   for k, w in (("five", self.limits.five), ("week", self.limits.week)))

    def _animate(self):
        for key, window in (("five", self.limits.five), ("week", self.limits.week)):
            shown = self._shown.get(key)
            if window is None or shown is None:
                continue
            target = window.pct
            self._shown[key] = target if abs(target - shown) < 0.3 else shown + (target - shown) * 0.22
        if not self._anim_pending():
            self.anim.stop()
        self.update()

    # --- eventos ----------------------------------------------------------------
    def enterEvent(self, e):
        self.leave_timer.stop()
        if not self._hover:
            self._hover = True
            self.relayout()

    def leaveEvent(self, e):
        self.leave_timer.start()

    def _end_hover(self):
        if self._hover and not self.underMouse():
            self._hover = False
            self.relayout()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._origin = self.pos()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if abs(delta.x()) + abs(delta.y()) > 3:
            self._moved = True
        if self._moved:
            self.move(self._origin + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            self.toggle_panel()
            return
        if e.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        if self._moved:
            self.cfg["x"], self.cfg["y"] = self.x() + M, self.y() + M
            self.save()
            return
        _, _, layout = self._style_layout()
        action = layout.hit(e.position().x() - M, e.position().y() - M)
        if action == "options":
            self.toggle_panel()
        elif action == "refresh":
            self.refresh(reschedule=False)

    def mouseDoubleClickEvent(self, e):
        if self.cfg["style"] == "clasico":
            self.set_size("full" if self.cfg["size"] == "compact" else "compact")

    def toggle_panel(self):
        if self._panel is not None and self._panel.isVisible():
            self._panel.close()
            return
        self._panel = Panel(self)
        self._panel.show()

    # --- dibujo -----------------------------------------------------------------
    def paintEvent(self, e):
        ctx, style, layout = self._style_layout()
        if self._layout is None or (layout.w, layout.h) != (self._layout.w, self._layout.h):
            QTimer.singleShot(0, self.relayout)  # el estilo cambio de tamano (p. ej. texto mas largo)
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.translate(M, M)
        style.paint(p, ctx, layout)

    def place(self):
        area = self.screen().availableGeometry()
        x, y = self.cfg["x"], self.cfg["y"]
        if x is None or y is None:
            x, y = area.right() - self._layout.w - 24, area.top() + 24
        x = max(area.left(), min(x - M, area.right() - 60))
        y = max(area.top(), min(y - M, area.bottom() - 60))
        self.move(x, y)
