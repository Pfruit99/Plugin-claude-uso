"""Widget de uso de Claude con interfaz Qt (PySide6): antialiasing, degradados y sombra suave.

Reutiliza de widget.py toda la logica (limites, tokens, configuracion); aqui solo se dibuja.
"""
import ctypes
import logging
import math
import sys
import threading
import time
from datetime import datetime, timedelta

import struct
from pathlib import Path

from PySide6.QtCore import (QBuffer, QByteArray, QEasingCurve, QIODevice, QObject, QPoint, QPointF, QPropertyAnimation,
                            QRectF, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont, QFontDatabase, QFontMetricsF, QIcon,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSlider, QSpinBox, QSystemTrayIcon, QVBoxLayout, QWidget)

import widget as core

APP_NAME = "Claude Usage Widget"
VERSION = "0.0.5"
CODENAME = "Aurora"
AUTHOR = "Pfruit99"
APP_ID = "Pfruit99.ClaudeUsageWidget"
ICON_FILE = Path(__file__).resolve().parent / "assets" / "icon.ico"

M = 14  # margen transparente alrededor de la tarjeta, para la sombra
PAD = core.PAD
WIDTHS = {"compact": 290, "full": 330}
WINDOW_SECONDS = {"five": 5 * 3600, "week": 7 * 86400}

# (tono claro del inicio del arco, color del final) por nivel
LEVELS = {core.OK: "#5DCAA5", core.WARN: "#E8B04A", core.BAD: "#F09595"}

GLYPHS_FLUENT = dict(settings="", refresh="", close="", warning="",
                     light="", dark="")
GLYPHS_SYMBOL = dict(settings="⚙", refresh="↻", close="✕", warning="⚠", light="☀", dark="☾")


def qc(color, alpha=255):
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def icon_pixmap(size):
    """Icono de la app: cuadrado coral con un anillo de progreso, dibujado a cualquier tamano."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(core.ACCENT).lighter(118))
    grad.setColorAt(1, QColor(core.ACCENT).darker(118))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(size * 0.03, size * 0.03, size * 0.94, size * 0.94), size * 0.24, size * 0.24)
    ring = QRectF(size * 0.27, size * 0.27, size * 0.46, size * 0.46)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 70), size * 0.12))
    p.drawEllipse(ring)
    p.setPen(QPen(QColor("#FFFFFF"), size * 0.12, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(ring, 90 * 16, -250 * 16)
    p.end()
    return pm


def make_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon


def export_ico(path):
    """Escribe un .ico con varios tamanos (PNG dentro): para el acceso directo de Windows."""
    images = []
    for size in (16, 32, 48, 64, 256):
        data, buf = QByteArray(), None
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        icon_pixmap(size).save(buf, "PNG")
        images.append((size, bytes(data)))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, png in images:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out + b"".join(png for _, png in images))


class Fonts:
    """Elige una vez la mejor fuente de texto y de iconos disponible en este Windows."""

    def __init__(self):
        families = set(QFontDatabase.families())
        self.text = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in families), "Segoe UI")
        icon = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
        self.icon = icon or "Segoe UI Symbol"
        self.glyph = GLYPHS_FLUENT if icon else GLYPHS_SYMBOL

    def make(self, size, bold=False, icon=False):
        f = QFont(self.icon if icon else self.text)
        f.setPointSizeF(size)
        if bold:
            f.setWeight(QFont.DemiBold)
        return f


class Bridge(QObject):
    tokens_ready = Signal()


def draw_text(p, x, y, s, color, font, anchor="w"):
    """Texto con ancla (w = izquierda, e = derecha, c = centro) centrado en vertical sobre y."""
    p.setFont(font)
    p.setPen(QColor(color))
    box = QRectF(x - (400 if anchor == "e" else 200 if anchor == "c" else 0), y - 16, 400, 32)
    flags = {"w": Qt.AlignLeft, "e": Qt.AlignRight, "c": Qt.AlignHCenter}[anchor]
    p.drawText(box, int(flags | Qt.AlignVCenter | Qt.TextDontClip), s)


def pace_fraction(window, span):
    """Fraccion de la ventana ya transcurrida (None si no se conoce el reinicio)."""
    if window is None or window[1] is None:
        return None
    return max(0.0, min(1.0, 1 - (window[1] - time.time()) / span))


class Panel(QWidget):
    """Panel flotante de opciones: se arrastra desde cualquier zona libre, queda abierto y se atenua
    cuando el raton no esta encima para no estorbar a otras ventanas."""

    W, SEG_H, ACT_H, PADX, HEAD = 236, 40, 34, 14, 30
    DIM = 0.55  # opacidad relativa cuando el raton no esta encima

    def __init__(self, app):
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        if app.cfg["topmost"]:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.app, self.hover, self._drag, self._moved = app, None, None, False
        self._build()
        self.setFixedSize(self.W + 2 * M, self.h + 2 * M)
        self.setWindowOpacity(app.cfg["opacity"] / 100)
        self.move(self._start_pos())

    def _start_pos(self):
        """Ultima posicion usada; si no hay, junto al widget (a un lado) para no taparlo."""
        area, cfg, card = self.app.screen().availableGeometry(), self.app.cfg, self.app
        x, y = cfg.get("panel_x"), cfg.get("panel_y")
        if not isinstance(x, int) or not isinstance(y, int):
            x = card.x() + card.width() + 4
            if x + self.width() > area.right():
                x = card.x() - self.width() - 4
            y = card.y()
        return QPoint(max(area.left(), min(x, area.right() - self.width() - 8)),
                      max(area.top(), min(y, area.bottom() - self.height() - 8)))

    def _build(self):
        self.segs, self.btns, self.acts = [], [], []
        self.close_rect = QRectF(self.W - 34, 4, 26, 22)
        y = self.HEAD + 4
        for label, key, options in (("Vista", "view", ("ring", "bar")),
                                    ("Tamaño", "size", ("compact", "full")),
                                    ("Tema", "theme", ("auto", "light", "dark"))):
            self.segs.append((label, key, y))
            x2 = self.W - self.PADX
            for value in reversed(options):
                rect = QRectF(x2 - 36, y + 6, 36, self.SEG_H - 12)
                self.btns.append((rect, ("set", key, value), value))
                x2 -= 40
            y += self.SEG_H
        self.sep_y = y + 4
        y += 10
        g = self.app.fonts.glyph
        for glyph, label, name, bad, hint in ((g["settings"], "Ajustes…", "settings", False, ""),
                                              (g["refresh"], "Actualizar ahora", "refresh", False, "R"),
                                              (g["close"], "Salir", "exit", True, "")):
            self.acts.append((QRectF(6, y, self.W - 12, self.ACT_H), ("act", name), glyph, label, bad, hint))
            y += self.ACT_H
        self.h = y + 8

    def showEvent(self, e):
        super().showEvent(e)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)  # aparece suavemente
        self._fade.setDuration(140)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(self.app.cfg["opacity"] / 100)
        self._fade.start()
        QTimer.singleShot(1800, self._dim_if_idle)

    def _dim_if_idle(self):
        if self.isVisible() and not self.underMouse() and self._drag is None:
            self.setWindowOpacity(self._base_opacity() * self.DIM)

    def _hit(self, pos):
        pt = QPointF(pos.x() - M, pos.y() - M)
        if self.close_rect.contains(pt):
            return ("act", "close")
        for rect, action, *_ in self.btns + self.acts:
            if rect.contains(pt):
                return action
        return None

    def _base_opacity(self):
        return self.app.cfg["opacity"] / 100

    def enterEvent(self, e):
        self.setWindowOpacity(self._base_opacity())

    def leaveEvent(self, e):
        self.hover = None
        if self._drag is None:
            self.setWindowOpacity(self._base_opacity() * self.DIM)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._hit(e.position()) is None:
            self._drag = e.globalPosition().toPoint() - self.pos()  # zona libre: arrastrar
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self._moved = True
            self.move(e.globalPosition().toPoint() - self._drag)
            return
        hit = self._hit(e.position())
        self.setCursor(Qt.PointingHandCursor if hit else Qt.SizeAllCursor)
        if hit != self.hover:
            self.hover = hit
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            if self._moved:
                self.app.cfg["panel_x"], self.app.cfg["panel_y"] = self.x(), self.y()
                core.save_config(self.app.cfg)
            return
        action = self._hit(e.position())
        if action:
            self._run(action)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() == Qt.Key_R:
            self._run(("act", "refresh"))

    def _run(self, action):
        app = self.app
        if action[0] == "set":
            {"view": app.set_view, "size": app.set_size, "theme": app.set_theme}[action[1]](action[2])
            self.update()
            return
        if action[1] == "close":
            self.close()
            return
        {"settings": app.open_settings, "exit": QApplication.quit,
         "refresh": lambda: app.refresh(reschedule=False)}[action[1]]()

    def paintEvent(self, e):
        app, cfg, f = self.app, self.app.cfg, self.app.fonts
        pal = app.palette_()
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        app.draw_shadow(p, self.W, self.h, 14)
        p.translate(M, M)
        card = QPainterPath()
        card.addRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.h - 1), 14, 14)
        p.setBrush(qc(pal["bg"], 245))
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawPath(card)

        # cabecera: asa de arrastre (puntos), titulo y cerrar
        p.setPen(Qt.NoPen)
        p.setBrush(qc(pal["muted"], 150))
        for i in range(3):
            for j in range(2):
                p.drawEllipse(QPointF(self.W / 2 - 8 + i * 8, 11 + j * 6), 1.4, 1.4)
        draw_text(p, self.PADX + 2, 15, "Opciones", pal["muted"], f.make(9))
        if self.hover == ("act", "close"):
            p.setBrush(QColor(core.BAD))
            p.drawRoundedRect(self.close_rect, 7, 7)
        draw_text(p, self.close_rect.center().x(), self.close_rect.center().y(), f.glyph["close"],
                  "#FFFFFF" if self.hover == ("act", "close") else pal["muted"], f.make(9, icon=True), "c")

        for label, key, y in self.segs:
            draw_text(p, self.PADX + 2, y + self.SEG_H / 2, label, pal["text"], f.make(10))
        for rect, action, value in self.btns:
            active = cfg[action[1]] == value
            fill = core.ACCENT if active else (pal["border"] if self.hover == action else pal["track"])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(fill))
            p.drawRoundedRect(rect, 8, 8)
            self._icon(p, value, rect.center(), "#FFFFFF" if active else pal["sub"])
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawLine(QPointF(self.PADX, self.sep_y), QPointF(self.W - self.PADX, self.sep_y))
        for rect, action, glyph, label, bad, hint in self.acts:
            color = core.BAD if bad else pal["text"]
            if self.hover == action:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal["track"]))
                p.drawRoundedRect(rect, 8, 8)
            cy = rect.center().y()
            draw_text(p, self.PADX + 8, cy, glyph, color, f.make(11, icon=True), "c")
            draw_text(p, self.PADX + 30, cy, label, color, f.make(10))
            if hint:
                draw_text(p, self.W - self.PADX - 4, cy, hint, pal["muted"], f.make(9), "e")

    def _icon(self, p, kind, c, color):
        f, g = self.app.fonts, self.app.fonts.glyph
        col = QColor(color)
        p.setBrush(Qt.NoBrush)
        if kind == "ring":
            p.setPen(QPen(col, 1.3))
            p.drawEllipse(c, 7, 7)
            p.setPen(QPen(col, 3.2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(c.x() - 7, c.y() - 7, 14, 14), 90 * 16, -250 * 16)
        elif kind == "bar":
            p.setPen(QPen(col, 1.3))
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 3, 16, 6), 3, 3)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 3, 10, 6), 3, 3)
        elif kind == "compact":
            p.setPen(QPen(col, 1.6))
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 4, 16, 8), 2, 2)
        elif kind == "full":
            p.setPen(QPen(col, 1.6))
            p.drawRoundedRect(QRectF(c.x() - 7, c.y() - 9, 14, 18), 2, 2)
            p.drawLine(QPointF(c.x() - 7, c.y() - 3), QPointF(c.x() + 7, c.y() - 3))
        elif kind == "auto":
            draw_text(p, c.x(), c.y(), "A", color, f.make(11, bold=True), "c")
        else:
            draw_text(p, c.x(), c.y(), g[kind], color, f.make(11, icon=True), "c")


class SettingsDialog(QDialog):
    """Ajustes: ventana sin marco que se despliega con animacion y se mueve desde su barra de titulo."""

    BODY_W, TITLE_H = 340, 44

    def __init__(self, app):
        super().__init__(app, Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.app, self._closing, self._drag = app, False, None
        self._h = float(self.TITLE_H)
        pal, f = app.palette_(), app.fonts
        self.setWindowTitle(f"Ajustes · {APP_NAME}")
        self.setWindowIcon(make_icon())
        self.setStyleSheet(f"""
            QLabel, QCheckBox {{ color: {pal['text']}; font-size: 10pt; }}
            QLabel#section {{ color: {pal['muted']}; font-size: 9pt; font-weight: 600; margin-top: 8px; }}
            QLabel#title {{ font-size: 11pt; font-weight: 600; }}
            QLabel#about {{ color: {pal['muted']}; font-size: 8pt; }}
            QComboBox, QSpinBox {{ background: {pal['track']}; color: {pal['text']}; border: 1px solid {pal['border']};
                border-radius: 7px; padding: 4px 8px; min-width: 110px; }}
            QComboBox QAbstractItemView {{ background: {pal['bg']}; color: {pal['text']}; selection-background-color: {core.ACCENT}; }}
            QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {pal['track']}; }}
            QSlider::sub-page:horizontal {{ border-radius: 3px; background: {core.ACCENT}; }}
            QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px; background: #FFFFFF;
                border: 1px solid {pal['border']}; }}
            QPushButton {{ background: {pal['track']}; color: {pal['text']}; border: none; border-radius: 7px; padding: 6px 14px; }}
            QPushButton:hover {{ background: {pal['border']}; }}
            QPushButton#primary {{ background: {core.ACCENT}; color: white; }}
            QPushButton#x {{ background: transparent; padding: 4px 8px; }}
            QPushButton#x:hover {{ background: {core.BAD}; color: white; }}
        """)
        self.body = QWidget(self)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(18, 0, 18, 14)
        root.setSpacing(6)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(22, 22))
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        close = QPushButton(f.glyph["close"])
        close.setObjectName("x")
        close.setFont(f.make(10, icon=True))
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        head.addWidget(logo)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(close)
        head.setContentsMargins(0, 8, 0, 0)
        root.addLayout(head)

        def section(text):
            label = QLabel(text.upper())
            label.setObjectName("section")
            root.addWidget(label)

        def row(text, widget):
            line = QHBoxLayout()
            line.addWidget(QLabel(text))
            line.addStretch()
            line.addWidget(widget)
            root.addLayout(line)

        section("Apariencia")
        self.theme = QComboBox()
        self.theme.addItems([label for label, _ in core.THEME_CHOICES])
        self.theme.activated.connect(lambda i: app.apply("theme", core.THEME_CHOICES[i][1]))
        row("Tema", self.theme)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setFixedWidth(130)
        self.opacity_label = QLabel()
        self.opacity.valueChanged.connect(self._opacity)
        both = QHBoxLayout()
        both.setContentsMargins(0, 0, 0, 0)
        both.addWidget(self.opacity)
        both.addWidget(self.opacity_label)
        holder = QWidget()
        holder.setLayout(both)
        row("Opacidad", holder)

        section("Datos")
        self.refresh = QComboBox()
        self.refresh.addItems([label for label, _ in core.REFRESH_CHOICES])
        self.refresh.activated.connect(lambda i: app.apply("refresh", core.REFRESH_CHOICES[i][1]))
        row("Actualizar cada", self.refresh)
        self.spins = {}
        for key, text, lo, hi in (("warn", "Aviso amarillo desde (%)", 1, 98), ("bad", "Aviso rojo desde (%)", 2, 100)):
            spin = self.spins[key] = QSpinBox()
            spin.setRange(lo, hi)
            spin.valueChanged.connect(lambda v, k=key: app.apply(k, v))
            row(text, spin)

        section("Sistema")
        self.startup = QCheckBox("Iniciar con Windows")
        self.startup.toggled.connect(self._startup)
        root.addWidget(self.startup)

        buttons = QHBoxLayout()
        buttons.addStretch()
        reset, done = QPushButton("Restablecer"), QPushButton("Cerrar")
        done.setObjectName("primary")
        reset.clicked.connect(self._reset)
        done.clicked.connect(self.close)
        buttons.addWidget(reset)
        buttons.addWidget(done)
        root.addSpacing(8)
        root.addLayout(buttons)
        about = QLabel(f"{APP_NAME} · v{VERSION} «{CODENAME}»\nDesarrollado por {AUTHOR} con Claude Code")
        about.setObjectName("about")
        about.setAlignment(Qt.AlignCenter)
        root.addSpacing(6)
        root.addWidget(about)

        self._sync()
        self.full_h = self.body.sizeHint().height()
        self.body.setFixedSize(self.BODY_W, self.full_h)
        self.body.move(M, M)
        self.setFixedSize(self.BODY_W + 2 * M, self.TITLE_H + 2 * M)

        self.anim = QVariantAnimation(self)
        self.anim.setDuration(260)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._grow)
        self.anim.finished.connect(self._anim_done)

    def _sync(self):
        """Refleja la configuracion actual en los controles (sin disparar cambios)."""
        cfg = self.app.cfg
        controls = (self.theme, self.opacity, self.refresh, self.startup, *self.spins.values())
        for w in controls:
            w.blockSignals(True)
        self.theme.setCurrentIndex([v for _, v in core.THEME_CHOICES].index(cfg["theme"]))
        self.opacity.setValue(cfg["opacity"])
        self.opacity_label.setText(f"{cfg['opacity']} %")
        values = [v for _, v in core.REFRESH_CHOICES]
        self.refresh.setCurrentIndex(values.index(cfg["refresh"]) if cfg["refresh"] in values else 1)
        for key, spin in self.spins.items():
            spin.setValue(cfg[key])
        self.startup.setChecked(core.startup_enabled())
        for w in controls:
            w.blockSignals(False)

    # --- despliegue animado -----------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self._closing and self.anim.state() != QVariantAnimation.Running and self._h < self.full_h:
            self._play(0.0, 1.0)

    def _play(self, start, end):
        self.anim.stop()
        self.anim.setStartValue(start)
        self.anim.setEndValue(end)
        self.anim.start()

    def _grow(self, v):
        self._h = self.TITLE_H + (self.full_h - self.TITLE_H) * v
        self.setFixedHeight(int(self._h) + 2 * M)
        self.body.setMask(QRegion(0, 0, self.BODY_W, int(self._h)))
        self.setWindowOpacity(min(1.0, v * 1.8) * self.app.cfg["opacity"] / 100)
        self.update()

    def _anim_done(self):
        if self._closing:
            self.close()

    def closeEvent(self, e):
        if self._closing and self.anim.state() != QVariantAnimation.Running:
            e.accept()
            return
        e.ignore()  # primero se pliega, luego se cierra de verdad
        if not self._closing:
            self._closing = True
            running = self.anim.state() == QVariantAnimation.Running
            self._play(self.anim.currentValue() if running else 1.0, 0.0)

    def reject(self):
        self.close()

    # --- mover desde la barra de titulo ------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < M + self.TITLE_H:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def paintEvent(self, e):
        pal = self.app.palette_()
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        w, h = self.BODY_W, self._h
        self.app.draw_shadow(p, w, h, 16)
        p.translate(M, M)
        p.setBrush(qc(pal["bg"], 248))
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 16, 16)

    def _opacity(self, value):
        self.opacity_label.setText(f"{value} %")
        self.app.apply("opacity", value)

    def _startup(self, on):
        try:
            core.set_startup(on)
        except Exception:
            logging.exception("No se pudo cambiar el inicio con Windows")
        self.startup.blockSignals(True)
        self.startup.setChecked(core.startup_enabled())
        self.startup.blockSignals(False)

    def _reset(self):
        self.app.reset()
        self._sync()


class Card(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.cfg = core.load_config()
        self.fonts = Fonts()
        self.counter = core.TokenCounter()
        self.tokens = (0, 0)
        self.limits = (None, None, None, None)
        self.bridge = Bridge()
        self.bridge.tokens_ready.connect(self._relayout)
        self._busy = False
        self._tokens_at = 0.0
        self._shown = {}
        self._panel = self._settings = None
        self._hover = False
        self._press = None
        self._moved = False
        self.W, self.H = WIDTHS[self.cfg["size"]], 200

        self.anim = QTimer(self)
        self.anim.setInterval(core.ANIM_MS)
        self.anim.timeout.connect(self._animate)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.minute = QTimer(self)  # repinta las cuentas atras
        self.minute.setInterval(30_000)
        self.minute.timeout.connect(self.update)
        self.minute.start()

        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.cfg["topmost"])
        self.setWindowOpacity(self.cfg["opacity"] / 100)
        self.refresh()

    # --- configuracion ----------------------------------------------------------
    def palette_(self):
        theme = self.cfg["theme"]
        return core.THEMES[core.windows_theme() if theme == "auto" else theme]

    def _save(self):
        core.save_config(self.cfg)

    def set_view(self, v):
        self.cfg["view"] = v
        self._save()
        self._relayout()

    def set_size(self, v):
        self.cfg["size"] = v
        self._save()
        self._relayout()

    def set_theme(self, v):
        self.cfg["theme"] = v
        self._save()
        self.update()

    def apply(self, key, value):
        cfg = self.cfg
        cfg[key] = value
        core.sanitize_config(cfg)
        if key == "opacity":
            self.setWindowOpacity(cfg["opacity"] / 100)
        elif key == "refresh":
            self._schedule()
        elif key == "topmost":
            self.setWindowFlag(Qt.WindowStaysOnTopHint, cfg["topmost"])
            self.show()
        self._save()
        self._relayout()

    def reset(self):
        for key in core.RESETTABLE:
            self.apply(key, core.DEFAULT_CONFIG[key])

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
        self.limits = core.read_limits()
        self._relayout()
        if not self._busy and time.time() - self._tokens_at >= max(core.TOKENS_EVERY, self.cfg["refresh"]):
            self._busy = True
            self._tokens_at = time.time()
            threading.Thread(target=self._count_tokens, daemon=True).start()
        if reschedule:
            self._schedule()

    def _schedule(self):
        self.timer.start(self.cfg["refresh"] * 1000)

    def _count_tokens(self):
        try:
            week = self.limits[1]
            if week and week[1]:
                week_start = datetime.fromtimestamp(week[1] - 7 * 86400).astimezone()
            else:
                week_start = datetime.now().astimezone() - timedelta(days=7)
            self.tokens = self.counter.totals(week_start)
        except Exception:
            logging.exception("Error contando tokens")
        finally:
            self._busy = False
        self.bridge.tokens_ready.emit()

    def _exhausted(self):
        return [w for w in self.limits[:2] if w and w[0] >= 100]

    def _height(self):
        full, ring = self.cfg["size"] == "full", self.cfg["view"] == "ring"
        y = 44 + (38 if self._exhausted() else 0) + (20 if self.limits[0] is None and self.limits[1] is None else 0)
        y += (150 if full else 114) if ring else (134 if full else 90)
        return y + (60 if full else 0) + 8

    def _tooltip(self):
        def part(label, w):
            return f"{label} {round(w[0])}%" if w else f"{label} --"
        return f"{APP_NAME}\n{part('5 h', self.limits[0])} · {part('Semana', self.limits[1])}"

    def _relayout(self):
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.setToolTip(self._tooltip())
        self.W, self.H = WIDTHS[self.cfg["size"]], self._height()
        self.setFixedSize(self.W + 2 * M, self.H + 2 * M)
        self._kick_anim()
        self.update()

    # --- animacion --------------------------------------------------------------
    def _kick_anim(self):
        for key, window in (("five", self.limits[0]), ("week", self.limits[1])):
            if window is None:
                self._shown[key] = None
            elif self._shown.get(key) is None:
                self._shown[key] = 0.0
        if not self.anim.isActive() and self._anim_pending():
            self.anim.start()

    def _anim_pending(self):
        return any(w is not None and self._shown.get(k) != w[0]
                   for k, w in (("five", self.limits[0]), ("week", self.limits[1])))

    def _animate(self):
        for key, window in (("five", self.limits[0]), ("week", self.limits[1])):
            shown = self._shown.get(key)
            if window is None or shown is None:
                continue
            target = window[0]
            self._shown[key] = target if abs(target - shown) < 0.3 else shown + (target - shown) * 0.22
        if not self._anim_pending():
            self.anim.stop()
        self.update()

    def _win(self, key, i):
        w = self.limits[i]
        if w is None or self._shown.get(key) is None:
            return w
        return self._shown[key], w[1]

    # --- eventos ----------------------------------------------------------------
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

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
            self._popup()
            return
        if e.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        if self._moved:
            self.cfg["x"], self.cfg["y"] = self.x() + M, self.y() + M
            self._save()
            return
        lx, ly = e.position().x() - M, e.position().y() - M
        full = self.cfg["size"] == "full"
        if 0 <= ly < 40:
            if not full and lx > self.W - 44 or full and PAD + 104 < lx < PAD + 144:
                self._popup()
            elif full and lx > self.W - 150:
                self.refresh(reschedule=False)

    def mouseDoubleClickEvent(self, e):
        self.set_size("full" if self.cfg["size"] == "compact" else "compact")

    def _popup(self):
        if self._panel is not None and self._panel.isVisible():
            self._panel.close()
            return
        self._panel = Panel(self)
        self._panel.show()

    # --- dibujo -----------------------------------------------------------------
    def draw_shadow(self, p, w, h, radius):
        p.setPen(Qt.NoPen)
        for i in range(M):
            p.setBrush(QColor(0, 0, 0, 5))
            p.drawRoundedRect(QRectF(i, i + 3, w + 2 * M - 2 * i, h + 2 * M - 2 * i), radius + M - i, radius + M - i)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        pal, W, H, f = self.palette_(), self.W, self.H, self.fonts
        five, week = self._win("five", 0), self._win("week", 1)
        updated, context = self.limits[2], self.limits[3]
        full, ring = self.cfg["size"] == "full", self.cfg["view"] == "ring"
        stale = bool(updated) and time.time() - updated > core.STALE_SECONDS
        exhausted = bool(self._exhausted())

        self.draw_shadow(p, W, H, 18)
        p.translate(M, M)
        card = QPainterPath()
        card.addRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 18, 18)
        p.setBrush(qc(pal["bg"], 244))
        p.setPen(QPen(QColor(core.BAD if exhausted else pal["border"]), 1))
        p.drawPath(card)
        p.save()  # brillo sutil en el borde superior, recortado a la tarjeta
        p.setClipPath(card)
        shine = QLinearGradient(0, 0, 0, 70)
        shine.setColorAt(0, QColor(255, 255, 255, 26 if pal["bg"] != "#FFFFFF" else 0))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(0, 0, W, 70), shine)
        p.restore()

        draw_text(p, PAD, 24, "Uso de Claude" if full else "Claude", pal["text"], f.make(12 if full else 11, True))
        icon_font = f.make(11, icon=True)
        if full:
            ago = f"{fmt_ago_text(updated)}"
            color = core.WARN if stale or not updated else pal["muted"]
            draw_text(p, W - PAD, 24, ago, color, f.make(9), "e")
            width = QFontMetricsF(f.make(9)).horizontalAdvance(ago)
            draw_text(p, W - PAD - width - 12, 24, f.glyph["refresh"], color, f.make(9, icon=True), "c")
            if self._hover:
                draw_text(p, PAD + 124, 24, f.glyph["settings"], pal["muted"], icon_font, "c")
        else:
            draw_text(p, W - PAD - 6, 24, f.glyph["settings"], pal["muted"], icon_font, "c")

        y = 44
        if exhausted:
            both = len(self._exhausted()) == 2
            msg = ("Límites de 5 h y semanal agotados" if both
                   else "Límite de 5 h agotado" if self.limits[0] and self.limits[0][0] >= 100
                   else "Límite semanal agotado")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal["banner_bg"]))
            p.drawRoundedRect(QRectF(PAD, y, W - 2 * PAD, 28), 9, 9)
            draw_text(p, PAD + 10, y + 14, f.glyph["warning"], pal["banner_text"], f.make(10, icon=True), "w")
            draw_text(p, PAD + 30, y + 14, msg, pal["banner_text"], f.make(9))
            y += 38
        if five is None and week is None:
            draw_text(p, PAD, y + 4, "Sin datos de límites: activa la línea de estado", core.WARN, f.make(8))
            y += 20

        y = self._rings(p, y, five, week, pal, full) if ring else self._bars(p, y, five, week, pal, full)

        if full:
            p.setPen(QPen(QColor(pal["border"]), 1))
            p.drawLine(QPointF(PAD, y + 4), QPointF(W - PAD, y + 4))
            today, wk = self.tokens
            stats = (("Hoy", core.fmt_tokens(today)), ("Semana", core.fmt_tokens(wk)),
                     ("Contexto", "--" if context is None else f"{round(context)}%"))
            inner = W - 2 * PAD
            for i, (label, value) in enumerate(stats):
                x = PAD + inner * (2 * i + 1) / 6
                draw_text(p, x, y + 22, label, pal["muted"], f.make(9), "c")
                draw_text(p, x, y + 42, value, pal["text"], f.make(13, True), "c")

    # anillos
    def _rings(self, p, y, five, week, pal, full):
        W = self.W
        r, w = (44, 10) if full else (32, 8)
        cy = y + (78 if full else 58)
        for cx, label, window, span in ((W * 0.25, "5 h", five, WINDOW_SECONDS["five"]),
                                        (W * 0.75, "Semana", week, WINDOW_SECONDS["week"])):
            self._ring(p, cx, cy, r, w, label, window, span, pal, full)
        return cy + r + (28 if full else 24)

    def _ring(self, p, cx, cy, r, w, label, window, span, pal, full):
        f = self.fonts
        pct = window[0] if window else None
        done = pct is not None and pct >= 100
        color = core.level_color(pct, self.cfg["warn"], self.cfg["bad"])
        draw_text(p, cx, cy - r - w / 2 - 10, label, pal["sub"], f.make(10 if full else 9), "c")
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(pal["track"]), w))
        p.drawEllipse(rect)
        if pct:
            frac = min(pct, 100) / 100
            grad = QConicalGradient(cx, cy, 90)
            grad.setColorAt(1.0, QColor(LEVELS.get(color, color)))
            grad.setColorAt(max(0.0, 1 - frac), QColor(color))
            if not done:
                glow = QPen(qc(color, 40), w + 7, Qt.SolidLine, Qt.RoundCap)
                p.setPen(glow)
                p.drawArc(rect, 90 * 16, int(-frac * 360 * 16))
            p.setPen(QPen(QBrush(grad), w, Qt.SolidLine, Qt.FlatCap if done else Qt.RoundCap))
            if done:
                p.drawEllipse(rect)
            else:
                p.drawArc(rect, 90 * 16, int(-frac * 360 * 16))
        pace = pace_fraction(window, span)
        if pace is not None and 0.02 < pace < 0.98:  # muesca: cuanto deberias llevar por tiempo
            ang = math.radians(90 - pace * 360)
            inner, outer = r - w / 2 - 2, r + w / 2 + 2
            p.setPen(QPen(qc(pal["text"], 150), 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + inner * math.cos(ang), cy - inner * math.sin(ang)),
                       QPointF(cx + outer * math.cos(ang), cy - outer * math.sin(ang)))
        draw_text(p, cx, cy, "--" if pct is None else f"{round(pct)}%", core.BAD if done else pal["text"],
                  f.make(17 if full else 13, True), "c")
        rem = core.fmt_remaining(window)
        draw_text(p, cx, cy + r + w / 2 + 14, f"vuelve en {rem}" if done else rem,
                  core.BAD if done else pal["sub"], f.make(9), "c")

    # barras
    def _bars(self, p, y, five, week, pal, full):
        if full:
            self._bar(p, y + 12, "Ventana de 5 horas", five, WINDOW_SECONDS["five"], pal, True)
            self._bar(p, y + 82, "Semanal", week, WINDOW_SECONDS["week"], pal, True)
            return y + 134
        self._bar(p, y + 16, "5 horas", five, WINDOW_SECONDS["five"], pal, False)
        self._bar(p, y + 62, "Semana", week, WINDOW_SECONDS["week"], pal, False)
        return y + 90

    def _bar(self, p, y, label, window, span, pal, full):
        f, w = self.fonts, self.W - 2 * PAD
        pct = window[0] if window else None
        done = pct is not None and pct >= 100
        rem = core.fmt_remaining(window)
        if full:
            draw_text(p, PAD, y, label, pal["text"], f.make(11))
            draw_text(p, PAD + w, y, "--" if pct is None else f"{round(pct)}%",
                      core.BAD if done else pal["sub"], f.make(11, True), "e")
            self._track(p, PAD, y + 14, w, 8, pct, window, span, pal)
            text = f"Vuelve en {rem}" if done else f"Se reinicia en {rem}"
            draw_text(p, PAD, y + 38, text, core.BAD if done else pal["muted"], f.make(9))
        else:
            right = "--" if pct is None else (f"100% · vuelve en {rem}" if done else f"{round(pct)}% · {rem}")
            draw_text(p, PAD, y, label, pal["text"], f.make(10))
            draw_text(p, PAD + w, y, right, core.BAD if done else pal["sub"], f.make(9), "e")
            self._track(p, PAD, y + 12, w, 6, pct, window, span, pal)

    def _track(self, p, x, y, w, h, pct, window, span, pal):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["track"]))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        if pct:
            color = core.level_color(pct, self.cfg["warn"], self.cfg["bad"])
            width = max(h, w * min(pct, 100) / 100)
            grad = QLinearGradient(x, 0, x + width, 0)
            grad.setColorAt(0, QColor(LEVELS.get(color, color)))
            grad.setColorAt(1, QColor(color))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(x, y, width, h), h / 2, h / 2)
        pace = pace_fraction(window, span)
        if pace is not None and 0.02 < pace < 0.98:
            px = x + w * pace
            p.setPen(QPen(qc(pal["text"], 150), 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(px, y - 3), QPointF(px, y + h + 3))

    def place(self):
        area = self.screen().availableGeometry()
        x, y = self.cfg["x"], self.cfg["y"]
        if x is None or y is None:
            x, y = area.right() - self.W - 24, area.top() + 24
        x = max(area.left(), min(x - M, area.right() - 60))
        y = max(area.top(), min(y - M, area.bottom() - 60))
        self.move(x, y)


def fmt_ago_text(updated):
    return core.fmt_ago(updated)


def setup_tray(card):
    """Icono en la bandeja: clic para mostrar u ocultar, menu con lo basico."""
    tray = QSystemTrayIcon(make_icon(), card)
    menu = QMenu()
    menu.addAction("Mostrar / ocultar", lambda: card.setVisible(not card.isVisible()))
    menu.addAction("Ajustes…", card.open_settings)
    menu.addAction("Actualizar ahora", lambda: card.refresh(reschedule=False))
    menu.addSeparator()
    menu.addAction(f"{APP_NAME} v{VERSION}").setEnabled(False)
    menu.addAction("Salir", QApplication.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: card.setVisible(not card.isVisible())
                           if reason == QSystemTrayIcon.Trigger else None)
    tray.setToolTip(card._tooltip())
    tray.show()
    card.tray, card._tray_menu = tray, menu


def main():
    if "--export-icon" in sys.argv:
        QApplication([])
        export_ico(ICON_FILE)
        return
    core.setup_logging()
    if not core.single_instance():
        return
    try:  # que Windows agrupe la barra de tareas con este icono y no con el de Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)  # el widget puede ocultarse y seguir en la bandeja
    card = Card()
    card.place()
    card.show()
    setup_tray(card)
    app.exec()


if __name__ == "__main__":
    main()
