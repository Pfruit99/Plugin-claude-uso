"""Lanzador sin consola: doble clic o `pythonw widget.pyw`. Usa Qt y, si falta PySide6, el widget Tk."""
try:
    from widget_qt import main
except ImportError:
    from widget import main

main()
