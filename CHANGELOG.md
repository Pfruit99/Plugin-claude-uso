# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

## [0.0.5] - 2026-10-22

### Changed
- El panel de opciones (Vista, Tamaño, Tema) ya no se cierra al hacer clic fuera: queda abierto, se arrastra desde cualquier zona libre, recuerda su posición y se cierra con la X o con Esc.
- Aparece junto al widget (sin taparlo) y se atenúa cuando el ratón no está encima.

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

