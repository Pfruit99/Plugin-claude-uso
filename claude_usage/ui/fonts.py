"""Seleccion de fuentes de texto e iconos disponibles en este Windows."""
from PySide6.QtGui import QFont, QFontDatabase

GLYPHS_FLUENT = dict(settings="", refresh="", close="", warning="", light="", dark="")
GLYPHS_SYMBOL = dict(settings="⚙", refresh="↻", close="✕", warning="⚠", light="☀", dark="☾")


class Fonts:
    """Elige una vez la mejor fuente de texto y de iconos y guarda las fuentes ya creadas."""

    def __init__(self):
        families = set(QFontDatabase.families())
        self.text = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in families), "Segoe UI")
        icon = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
        self.icon = icon or "Segoe UI Symbol"
        self.glyph = GLYPHS_FLUENT if icon else GLYPHS_SYMBOL
        self._cache = {}

    def make(self, size, bold=False, icon=False):
        key = (size, bold, icon)
        font = self._cache.get(key)
        if font is None:
            font = QFont(self.icon if icon else self.text)
            font.setPointSizeF(size)
            if bold:
                font.setWeight(QFont.DemiBold)
            font = self._cache[key] = font
        return font
