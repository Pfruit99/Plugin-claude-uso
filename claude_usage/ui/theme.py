"""Paletas, colores de nivel y medidas comunes."""
from ..status import FRENA, LIBRE, OJO, SIN_DATOS

M = 14    # margen transparente alrededor de la tarjeta, para la sombra
PAD = 18  # margen interior de la tarjeta

THEMES = {
    "light": dict(bg="#FFFFFF", border="#D3D1C7", track="#E8E6DE", text="#2C2C2A", sub="#5F5E5A",
                  muted="#888780", banner_bg="#FCEBEB", banner_text="#A32D2D"),
    "dark": dict(bg="#1E1E1C", border="#444441", track="#33332F", text="#F1EFE8", sub="#B4B2A9",
                 muted="#888780", banner_bg="#3B1010", banner_text="#F09595"),
}
OK, WARN, BAD = "#1D9E75", "#BA7517", "#E24B4A"
ACCENT = "#D97757"
NO_DATA = "#B4B2A9"

# Color del estado en la interfaz (algo mas vivo que el de las barras para leerse bien como palabra o luz)
STATUS_COLOR = {LIBRE: "#2FB88A", OJO: "#D9962B", FRENA: BAD, SIN_DATOS: NO_DATA}
# Tono claro con el que empieza el degradado de cada color
GRADIENT_START = {OK: "#5DCAA5", WARN: "#E8B04A", BAD: "#F09595", STATUS_COLOR[LIBRE]: "#5DCAA5",
                  STATUS_COLOR[OJO]: "#E8B04A"}


def level_color(pct, warn=70, bad=90):
    if pct is None:
        return NO_DATA
    return BAD if pct >= bad else WARN if pct >= warn else OK
