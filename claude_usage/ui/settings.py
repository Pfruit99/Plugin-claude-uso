"""Ventana de Ajustes: sin marco, se despliega con animacion y se mueve desde su barra de titulo."""
import logging

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPen, QColor, QRegion
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, AUTHOR, CODENAME, VERSION, winsys
from ..config import REFRESH_CHOICES, THEME_CHOICES
from .draw import draw_shadow, qc
from .icon import make_icon
from .theme import ACCENT, BAD, M


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
            QComboBox QAbstractItemView {{ background: {pal['bg']}; color: {pal['text']}; selection-background-color: {ACCENT}; }}
            QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: {pal['track']}; }}
            QSlider::sub-page:horizontal {{ border-radius: 3px; background: {ACCENT}; }}
            QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px; background: #FFFFFF;
                border: 1px solid {pal['border']}; }}
            QPushButton {{ background: {pal['track']}; color: {pal['text']}; border: none; border-radius: 7px; padding: 6px 14px; }}
            QPushButton:hover {{ background: {pal['border']}; }}
            QPushButton#primary {{ background: {ACCENT}; color: white; }}
            QPushButton#x {{ background: transparent; padding: 4px 8px; }}
            QPushButton#x:hover {{ background: {BAD}; color: white; }}
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
        self.theme.addItems([label for label, _ in THEME_CHOICES])
        self.theme.activated.connect(lambda i: app.apply("theme", THEME_CHOICES[i][1]))
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
        self.refresh.addItems([label for label, _ in REFRESH_CHOICES])
        self.refresh.activated.connect(lambda i: app.apply("refresh", REFRESH_CHOICES[i][1]))
        row("Actualizar cada", self.refresh)
        self.spins = {}
        for key, text, lo, hi in (("warn", "«Ojo» desde (%)", 1, 98), ("bad", "«Frena» desde (%)", 2, 100)):
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
        self.theme.setCurrentIndex([v for _, v in THEME_CHOICES].index(cfg["theme"]))
        self.opacity.setValue(cfg["opacity"])
        self.opacity_label.setText(f"{cfg['opacity']} %")
        values = [v for _, v in REFRESH_CHOICES]
        self.refresh.setCurrentIndex(values.index(cfg["refresh"]) if cfg["refresh"] in values else 1)
        for key, spin in self.spins.items():
            spin.setValue(cfg[key])
        self.startup.setChecked(winsys.startup_enabled())
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
        p.translate(M, M)
        draw_shadow(p, QRectF(0, 0, w, h), 16)
        p.setBrush(qc(pal["bg"], 248))
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 16, 16)

    def _opacity(self, value):
        self.opacity_label.setText(f"{value} %")
        self.app.apply("opacity", value)

    def _startup(self, on):
        try:
            winsys.set_startup(on)
        except Exception:
            logging.exception("No se pudo cambiar el inicio con Windows")
        self.startup.blockSignals(True)
        self.startup.setChecked(winsys.startup_enabled())
        self.startup.blockSignals(False)

    def _reset(self):
        self.app.reset()
        self._sync()
