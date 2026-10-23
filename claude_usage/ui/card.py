"""Ventana flotante: reune datos de los agentes, animacion y eventos; el dibujo lo hace el estilo elegido."""
import logging
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSystemTrayIcon, QWidget

from .. import APP_NAME, config, winsys
from ..agents import combine
from ..alerts import Alert, StateWatcher
from ..limits import Limits
from ..providers import PROVIDERS, STATE_TEXT, Reading, is_enabled
from ..providers.base import ERROR, OK, PENDIENTE
from ..providers.codex import start_login
from ..texts import WORDS
from ..tokens import TokenCounter
from .fonts import Fonts
from .fx import Fx, fx_active, make_fx
from .icon import make_icon
from .panel import Panel
from .settings import SettingsDialog
from .styles import STYLES
from .styles.base import Context
from .theme import THEMES, M

ANIM_MS = 16        # ~60 fps solo mientras un valor cambia
TOKENS_EVERY = 30
HOVER_LEAVE_MS = 250  # retardo al salir el raton, para que la pildora no parpadee
FX_MS = 50            # ~20 fps para el latido y el destello; solo corre cuando hay algo que animar
NOTIFY_MS = 8000
LOGIN_POLL_MS = 10_000  # tras pulsar "Iniciar sesion", se reintenta cada 10 s durante 2 minutos
LOGIN_POLLS = 12


class Bridge(QObject):
    tokens_ready = Signal()
    reading_ready = Signal(str, object)  # (agente, Reading) desde un hilo de lectura


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
        self.limits = Limits()   # limites de Claude (los de los demas agentes estan en self.readings)
        self.readings = {}       # agente -> ultimo Reading de los proveedores lentos
        self._polled = {}        # agente -> hora de la ultima consulta
        self._polling = set()    # agentes con una consulta en marcha
        self.bridge = Bridge()
        self.bridge.tokens_ready.connect(self.relayout)
        self.bridge.reading_ready.connect(self._on_reading)
        self._busy = False
        self._tokens_at = 0.0
        self._shown = {}
        self._panel = self._settings = self.tray = None
        self._hover = False
        self._press = self._origin = None
        self._moved = False
        self._layout = None
        self._login_ticks = 0
        self.watcher = StateWatcher()
        self._level = self._prev_level = self._changed_at = None  # para el fundido y el destello

        self.anim = QTimer(self)
        self.anim.setInterval(ANIM_MS)
        self.anim.timeout.connect(self._animate)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.minute = QTimer(self)  # actualiza las cuentas atras y el estado por ritmo
        self.minute.setInterval(30_000)
        self.minute.timeout.connect(self.relayout)
        self.minute.start()
        self.fx_timer = QTimer(self)
        self.fx_timer.setInterval(FX_MS)
        self.fx_timer.timeout.connect(self._fx_tick)
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.setInterval(HOVER_LEAVE_MS)
        self.leave_timer.timeout.connect(self._end_hover)
        self.save_timer = QTimer(self)  # agrupa guardados seguidos (p. ej. al mover el deslizador)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(lambda: config.save_config(self.cfg))
        self.login_timer = QTimer(self)
        self.login_timer.setInterval(LOGIN_POLL_MS)
        self.login_timer.timeout.connect(self._login_tick)

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
        elif key == "codex_enabled":
            if cfg["codex_enabled"]:
                self._poll_agents(force=True)
            else:
                self.readings.pop("codex", None)
                self.login_timer.stop()
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
        self._settings.destroyed.connect(self._forget_settings)  # evita usar una ventana ya borrada
        self._settings.show()
        self._settings.move(self.x(), self.y() + self.height() + 8)

    def _forget_settings(self, *_):
        self._settings = None

    # --- agentes ----------------------------------------------------------------
    def _items(self):
        """[(nombre, etiqueta, Reading)] de los agentes activos, con Claude primero."""
        items = [("claude", PROVIDERS["claude"].label, Reading(self.limits))]
        for name, provider in PROVIDERS.items():
            if name != "claude" and is_enabled(self.cfg, name):
                items.append((name, provider.label, self.readings.get(name) or Reading(Limits(), PENDIENTE)))
        return items

    def overview(self, now=None):
        return combine(self._items(), self.cfg["warn"], self.cfg["bad"], now)

    def agent_state_text(self, name):
        """Estado de un agente para Ajustes: Conectado, Sin sesion, No instalado..."""
        if not is_enabled(self.cfg, name):
            return "Desactivado"
        reading = self.readings.get(name)
        return STATE_TEXT[reading.state if reading else PENDIENTE]

    def _poll_agents(self, force=False):
        """Lanza la lectura de los agentes lentos: solo con el widget visible y cada `poll_seconds`."""
        now = time.time()
        for name, provider in PROVIDERS.items():
            if not provider.slow or not is_enabled(self.cfg, name) or name in self._polling:
                continue
            if not force and (not self.isVisible() or now - self._polled.get(name, 0) < provider.poll_seconds):
                continue
            self._polling.add(name)
            self._polled[name] = now
            threading.Thread(target=self._read_agent, args=(name,), daemon=True).start()

    def _read_agent(self, name):
        provider = PROVIDERS[name]
        try:
            provider.configure(self.cfg)
            reading = provider.read()
        except Exception:
            logging.exception("Error leyendo %s", name)
            reading = Reading(Limits(), ERROR, "Error inesperado")
        self.bridge.reading_ready.emit(name, reading)

    def _on_reading(self, name, reading):
        self._polling.discard(name)
        if not is_enabled(self.cfg, name):
            return
        self.readings[name] = reading
        if reading.state == OK:
            self.login_timer.stop()
        self._watch_state()
        self.relayout()

    def start_codex_login(self):
        """Activa Codex y lanza `codex login`; despues se reintenta la lectura hasta que haya sesion."""
        self.apply("codex_enabled", True)
        if not start_login(self.cfg["codex_path"]):
            return False
        self._login_ticks = 0
        self.login_timer.start()
        return True

    def _login_tick(self):
        self._login_ticks += 1
        reading = self.readings.get("codex")
        if self._login_ticks > LOGIN_POLLS or (reading and reading.state == OK):
            self.login_timer.stop()
        else:
            self._poll_agents(force=True)

    # --- datos ------------------------------------------------------------------
    def refresh(self, reschedule=True):
        """`reschedule=False` es una actualizacion manual: tambien consulta ya a los agentes lentos."""
        self.limits = PROVIDERS["claude"].read().limits
        self._poll_agents(force=not reschedule)
        self._watch_state()
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

    # --- avisos de Windows ------------------------------------------------------
    def _watch_state(self):
        now = time.time()
        ov = self.overview(now)
        agent = ov.chosen_label if ov.chosen not in (None, "claude") else None
        alert = self.watcher.update(ov.status, ov.stale, now, agent)  # siempre vigila; solo muestra si esta activado
        if alert and self.cfg["notify"]:
            self.notify(alert)

    def notify(self, alert):
        if self.tray is None or not QSystemTrayIcon.supportsMessages():
            return
        icon = QSystemTrayIcon.Warning if alert.warning else QSystemTrayIcon.Information
        self.tray.showMessage(alert.title, alert.message, icon, NOTIFY_MS)

    def test_notification(self):
        self.notify(Alert("prueba", "Aviso de prueba", "Así te avisará el widget cuando cambie el estado.", False))

    def tooltip(self):
        lines = [APP_NAME]
        for e in self.overview().entries:
            if e.usable:
                lines.append(f"{e.label}: {WORDS[e.status.level]} · {round(e.status.pct)} % de {e.status.label}")
            else:
                lines.append(f"{e.label}: {'sin datos' if e.state == OK else STATE_TEXT[e.state].lower()}")
        return "\n".join(lines)

    # --- contexto, tamano y animacion -------------------------------------------
    def _animated(self, slot, window):
        shown = self._shown.get(slot)
        return window if window is None or shown is None else replace(window, pct=shown)

    def _animated_limits(self, name, limits):
        return replace(limits, five=self._animated((name, "five"), limits.five),
                       week=self._animated((name, "week"), limits.week))

    def _context(self):
        now = time.time()
        cfg = self.cfg
        ov = self.overview(now)
        claude = next(e for e in ov.entries if e.name == "claude")
        chosen = ov.chosen_entry or claude
        claude_animated = self._animated_limits("claude", claude.limits)
        limits = claude_animated if chosen.name == "claude" else self._animated_limits(chosen.name, chosen.limits)
        return Context(limits=limits, real=chosen.limits, status=ov.status, tokens=self.tokens, cfg=cfg,
                       pal=self.palette_(), fonts=self.fonts, hover=self._hover, now=now,
                       fx=self._fx(ov.status.level, now), overview=ov, claude=claude_animated)

    def _fx(self, level, now):
        if not self.cfg["animations"]:
            return Fx()
        return make_fx(level, self._prev_level, self._changed_at, now)

    def _track_level(self, level, now):
        """Recuerda el estado anterior y cuando cambio, para el fundido y el destello."""
        if level != self._level:
            if self._level is not None:
                self._prev_level, self._changed_at = self._level, now
            self._level = level

    def _sync_fx_timer(self):
        active = (self.cfg["animations"] and self.isVisible()
                  and fx_active(self._level, self._changed_at, time.time()))
        if active != self.fx_timer.isActive():
            if active:
                self.fx_timer.start()
            else:
                self.fx_timer.stop()

    def _fx_tick(self):
        self.update()
        self._sync_fx_timer()

    def _style_layout(self):
        ctx = self._context()
        style = STYLES[self.cfg["style"]]
        return ctx, style, style.layout(ctx)

    def relayout(self):
        if self.tray is not None:
            self.tray.setToolTip(self.tooltip())
        self._track_level(self.overview().status.level, time.time())
        _, _, layout = self._style_layout()
        self._layout = layout
        self.setFixedSize(layout.w + 2 * M, layout.h + 2 * M)
        self._kick_anim()
        self._sync_fx_timer()
        self.update()

    def _slots(self):
        """[((agente, ranura), Window)] de todos los agentes activos, para animar sus porcentajes."""
        return [((e.name, key), window) for e in self.overview().entries
                for key, window in (("five", e.limits.five), ("week", e.limits.week))]

    def _kick_anim(self):
        for slot, window in self._slots():
            if window is None:
                self._shown[slot] = None
            elif self._shown.get(slot) is None:
                self._shown[slot] = 0.0
        if not self.anim.isActive() and self._anim_pending():
            self.anim.start()

    def _anim_pending(self):
        return any(w is not None and self._shown.get(s) != w.pct for s, w in self._slots())

    def _animate(self):
        for slot, window in self._slots():
            shown = self._shown.get(slot)
            if window is None or shown is None:
                continue
            target = window.pct
            self._shown[slot] = target if abs(target - shown) < 0.3 else shown + (target - shown) * 0.22
        if not self._anim_pending():
            self.anim.stop()
        self.update()

    # --- eventos ----------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._sync_fx_timer()
        self._poll_agents()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._sync_fx_timer()  # oculto en la bandeja: sin animaciones

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
