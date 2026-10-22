# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

## [0.05] «Aurora»

Desarrollado por Pfruit99 con Claude Code.

### Added
- Interfaz Qt (PySide6) con antialiasing, degradados, sombra suave y marca de ritmo; si falta PySide6 se usa la versión Tk.
- Icono propio (`assets/icon.ico`) en ventanas, bandeja y acceso directo de inicio.
- Icono en la bandeja del sistema con menú y uso en el tooltip.
- Ajustes sin marco con animación de despliegue, movible, con versión y créditos.
- Panel de opciones con fundido de entrada.

### Changed
- `widget.pyw` arranca la versión Qt y cae a Tk si no hay PySide6.

