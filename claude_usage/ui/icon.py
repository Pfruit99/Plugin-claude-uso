"""Icono de la app dibujado a cualquier tamano, y exportacion a .ico para el acceso directo."""
import struct
from functools import cache

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap

from ..winsys import ICON_FILE
from .theme import ACCENT


def icon_pixmap(size):
    """Cuadrado coral con un anillo de progreso."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(ACCENT).lighter(118))
    grad.setColorAt(1, QColor(ACCENT).darker(118))
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


@cache
def make_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon


def export_ico(path=ICON_FILE):
    """Escribe un .ico con varios tamanos (PNG dentro)."""
    images = []
    for size in (16, 32, 48, 64, 256):
        data = QByteArray()
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
