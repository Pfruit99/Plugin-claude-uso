"""Panel flotante de opciones: estilo, vista, tamano y tema, mas acciones. Queda abierto y se atenua."""
from PySide6.QtCore import QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ..config import STYLE_CHOICES
from .draw import draw_shadow, draw_text, qc
from .theme import ACCENT, BAD, M


class Panel(QWidget):
    """Se arrastra desde cualquier zona libre, queda abierto y se atenua cuando el raton no esta encima."""

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
        if x is None or y is None:
            x = card.x() + card.width() + 4
            if x + self.width() > area.right():
                x = card.x() - self.width() - 4
            y = card.y()
        return QPoint(max(area.left(), min(x, area.right() - self.width() - 8)),
                      max(area.top(), min(y, area.bottom() - self.height() - 8)))

    def _rows(self):
        """Filas de selectores; Vista y Tamano solo tienen sentido en el estilo Clasico."""
        rows = [("Estilo", "style", tuple(v for _, v in STYLE_CHOICES))]
        if self.app.cfg["style"] == "clasico":
            rows += [("Vista", "view", ("ring", "bar")), ("Tamaño", "size", ("compact", "full"))]
        rows.append(("Tema", "theme", ("auto", "light", "dark")))
        return rows

    def _build(self):
        self.segs, self.btns, self.acts = [], [], []
        self.close_rect = QRectF(self.W - 34, 4, 26, 22)
        y = self.HEAD + 4
        for label, key, options in self._rows():
            self.segs.append((label, key, y))
            x2 = self.W - self.PADX
            for value in reversed(options):
                self.btns.append((QRectF(x2 - 36, y + 6, 36, self.SEG_H - 12), ("set", key, value), value))
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

    def _rebuild(self):
        self._build()
        self.setFixedSize(self.W + 2 * M, self.h + 2 * M)

    def showEvent(self, e):
        super().showEvent(e)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)  # aparece suavemente
        self._fade.setDuration(140)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(self._base_opacity())
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
                self.app.save()
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
            {"style": app.set_style, "view": app.set_view, "size": app.set_size,
             "theme": app.set_theme}[action[1]](action[2])
            self._rebuild()  # el estilo cambia que filas se ven
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
        p.translate(M, M)
        draw_shadow(p, QRectF(0, 0, self.W, self.h), 14)
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
            p.setBrush(QColor(BAD))
            p.drawRoundedRect(self.close_rect, 7, 7)
        draw_text(p, self.close_rect.center().x(), self.close_rect.center().y(), f.glyph["close"],
                  "#FFFFFF" if self.hover == ("act", "close") else pal["muted"], f.make(9, icon=True), "c")

        for label, key, y in self.segs:
            draw_text(p, self.PADX + 2, y + self.SEG_H / 2, label, pal["text"], f.make(10))
        for rect, action, value in self.btns:
            active = cfg[action[1]] == value
            fill = ACCENT if active else (pal["border"] if self.hover == action else pal["track"])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(fill))
            p.drawRoundedRect(rect, 8, 8)
            self._icon(p, value, rect.center(), "#FFFFFF" if active else pal["sub"])
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawLine(QPointF(self.PADX, self.sep_y), QPointF(self.W - self.PADX, self.sep_y))
        for rect, action, glyph, label, bad, hint in self.acts:
            color = BAD if bad else pal["text"]
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
        if kind in ("ring", "clasico"):
            p.setPen(QPen(col, 1.3))
            p.drawEllipse(c, 7, 7)
            p.setPen(QPen(col, 3.2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(c.x() - 7, c.y() - 7, 14, 14), 90 * 16, -250 * 16)
        elif kind == "semaforo":
            p.setPen(Qt.NoPen)
            p.setBrush(qc(color, 70))
            p.drawEllipse(c, 8, 8)
            p.setBrush(col)
            p.drawEllipse(c, 4.5, 4.5)
        elif kind == "margen":
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 1, 16, 3), 1.5, 1.5)
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 6, 9, 3), 1.5, 1.5)
            p.setPen(QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(c.x() + 3, c.y() - 4), QPointF(c.x() + 3, c.y() + 4))
        elif kind == "pildora":
            p.setPen(QPen(col, 1.6))
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 4, 16, 8), 4, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(c.x() - 3.5, c.y()), 1.8, 1.8)
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
