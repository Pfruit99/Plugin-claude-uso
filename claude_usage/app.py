"""Arranque de la aplicacion: log, instancia unica, ventana flotante e icono de bandeja."""
import ctypes
import logging
import sys
import threading

from . import APP_ID, APP_NAME, VERSION, winsys


def setup_tray(card):
    """Icono en la bandeja: clic para mostrar u ocultar, menu con lo basico."""
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
    from .ui.icon import make_icon

    tray = QSystemTrayIcon(make_icon(), card)
    menu = QMenu()
    menu.addAction("Mostrar / ocultar", lambda: card.setVisible(not card.isVisible()))
    menu.addAction("Opciones", card.toggle_panel)
    menu.addAction("Ajustes…", card.open_settings)
    menu.addAction("Actualizar ahora", lambda: card.refresh(reschedule=False))
    menu.addSeparator()
    menu.addAction(f"{APP_NAME} v{VERSION}").setEnabled(False)
    menu.addAction("Salir", QApplication.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: card.setVisible(not card.isVisible())
                           if reason == QSystemTrayIcon.Trigger else None)
    tray.setToolTip(card.tooltip())
    tray.show()
    card.tray, card._tray_menu = tray, menu


def main():
    winsys.setup_logging()
    try:
        from PySide6.QtWidgets import QApplication
        from .ui.card import Card
        from .ui.icon import ICON_FILE, export_ico, make_icon
    except ImportError as exc:
        logging.exception("No se pudo cargar PySide6")
        winsys.show_error(APP_NAME, "Falta PySide6. Instálalo con:\n\n    pip install PySide6-Essentials\n\n"
                                    f"Detalle: {exc}")
        return
    if "--export-icon" in sys.argv:
        QApplication([])
        export_ico(ICON_FILE)
        return
    if not winsys.single_instance():
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
    app.aboutToQuit.connect(card.flush_save)
    threading.Thread(target=winsys.refresh_startup, daemon=True).start()
    app.exec()
