"""Registro de estilos: la clave coincide con el valor de `style` en la configuracion."""
from .clasico import Clasico
from .margen import Margen
from .pildora import Pildora
from .semaforo import Semaforo

STYLES = {"semaforo": Semaforo(), "margen": Margen(), "pildora": Pildora(), "clasico": Clasico()}
