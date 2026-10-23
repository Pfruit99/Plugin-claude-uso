"""Primitivas de dibujo compartidas por todos los estilos."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QConicalGradient, QLinearGradient, QPainterPath, QPen, QPixmap, QPainter

from .theme import GRADIENT_START, M

_shadows = {}


def qc(color, alpha=255):
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def draw_text(p, x, y, s, color, font, anchor="w"):
    """Texto con ancla (w = izquierda, e = derecha, c = centro) centrado en vertical sobre y."""
    p.setFont(font)
    p.setPen(QColor(color))
    box = QRectF(x - (400 if anchor == "e" else 200 if anchor == "c" else 0), y - 16, 400, 32)
    flags = {"w": Qt.AlignLeft, "e": Qt.AlignRight, "c": Qt.AlignHCenter}[anchor]
    p.drawText(box, int(flags | Qt.AlignVCenter | Qt.TextDontClip), s)


def _shadow_pixmap(w, h, radius):
    key = (round(w), round(h), radius)
    pm = _shadows.get(key)
    if pm is None:
        if len(_shadows) > 24:
            _shadows.clear()
        pm = QPixmap(key[0] + 2 * M, key[1] + 2 * M)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHints(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 5))
        for i in range(M):
            grow = M - i
            p.drawRoundedRect(QRectF(M - grow, M - grow + 3, key[0] + 2 * grow, key[1] + 2 * grow), radius + grow,
                              radius + grow)
        p.end()
        pm = _shadows[key] = pm
    return pm


def draw_shadow(p, rect, radius):
    """Sombra suave alrededor de `rect` (en las coordenadas actuales del painter); se dibuja una vez y se reutiliza."""
    p.drawPixmap(int(rect.x()) - M, int(rect.y()) - M, _shadow_pixmap(rect.width(), rect.height(), radius))


def draw_card(p, rect, pal, radius=18, border=None, shine=True, flash=None):
    """Fondo de tarjeta: sombra, relleno, borde y un brillo sutil arriba; flash = (color, 0..1) añade un destello."""
    draw_shadow(p, rect, radius)
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.setBrush(qc(pal["bg"], 244))
    p.setPen(QPen(QColor(border or pal["border"]), 1))
    p.drawPath(path)
    if shine and pal["bg"] != "#FFFFFF":
        p.save()
        p.setClipPath(path)
        grad = QLinearGradient(0, rect.y(), 0, rect.y() + 70)
        grad.setColorAt(0, QColor(255, 255, 255, 26))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(rect.x(), rect.y(), rect.width(), 70), grad)
        p.restore()
    if flash and flash[1] > 0.01:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(qc(flash[0], int(220 * flash[1])), 1 + 2.5 * flash[1]))
        p.drawPath(path)


def draw_dot(p, cx, cy, r, color, pulse=None):
    """Luz de estado con un halo suave; pulse (0..1) hace latir el halo."""
    halo, alpha = (r + 5, 50) if pulse is None else (r + 3 + 5 * pulse, 30 + int(70 * pulse))
    p.setPen(Qt.NoPen)
    p.setBrush(qc(color, alpha))
    p.drawEllipse(QPointF(cx, cy), halo, halo)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(cx, cy), r, r)


def draw_pace_tick(p, x, y1, y2, pal):
    p.setPen(QPen(qc(pal["text"], 150), 2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x, y1), QPointF(x, y2))


def draw_ring(p, cx, cy, r, w, pct, color, pal, pace=None):
    """Anillo de progreso con degradado, brillo y marca de ritmo; pct = None dibuja solo la pista."""
    done = pct is not None and pct >= 100
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(pal["track"]), w))
    p.drawEllipse(rect)
    if pct:
        frac = min(pct, 100) / 100
        grad = QConicalGradient(cx, cy, 90)
        grad.setColorAt(1.0, QColor(GRADIENT_START.get(color, color)))
        grad.setColorAt(max(0.0, 1 - frac), QColor(color))
        if not done:
            p.setPen(QPen(qc(color, 40), w + 7, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, int(-frac * 360 * 16))
        p.setPen(QPen(QBrush(grad), w, Qt.SolidLine, Qt.FlatCap if done else Qt.RoundCap))
        if done:
            p.drawEllipse(rect)
        else:
            p.drawArc(rect, 90 * 16, int(-frac * 360 * 16))
    if pace is not None and 0.02 < pace < 0.98:  # muesca: cuanto deberias llevar por tiempo
        ang = math.radians(90 - pace * 360)
        inner, outer = r - w / 2 - 2, r + w / 2 + 2
        p.setPen(QPen(qc(pal["text"], 150), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + inner * math.cos(ang), cy - inner * math.sin(ang)),
                   QPointF(cx + outer * math.cos(ang), cy - outer * math.sin(ang)))


def draw_track(p, x, y, w, h, pct, color, pal, pace=None, ghost=False):
    """Barra con degradado y marca de ritmo; con ghost=True sombrea el margen entre el uso y el ritmo."""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(pal["track"]))
    p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
    width = 0.0
    if pct:
        width = max(h, w * min(pct, 100) / 100)
        grad = QLinearGradient(x, 0, x + width, 0)
        grad.setColorAt(0, QColor(GRADIENT_START.get(color, color)))
        grad.setColorAt(1, QColor(color))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(x, y, width, h), h / 2, h / 2)
    if pace is not None and 0.02 < pace < 0.98:
        px = x + w * pace
        if ghost and px > x + width:
            p.setBrush(qc(color, 70))
            p.drawRoundedRect(QRectF(x + width - h / 2, y, px - x - width + h / 2, h), h / 2, h / 2)
        draw_pace_tick(p, px, y - 3, y + h + 3, pal)
