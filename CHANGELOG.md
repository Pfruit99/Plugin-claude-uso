# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

## [0.3.0] - 2026-10-23

### Added
- **Límites de Codex** junto a los de Claude. Se activan en Ajustes → Agentes («Mostrar límites de Codex») con la sesión de tu cuenta de ChatGPT; el botón «Iniciar sesión…» abre el inicio de sesión de Codex en el navegador. El widget nunca lee ni guarda tu token: pregunta a `codex app-server`, cada 5 minutos y solo con el widget visible, con tiempo máximo de 15 s y sin dejar procesos abiertos.
- El widget muestra el estado del **mejor agente disponible** y dice con cuál seguir: si Claude frena y Codex está libre, aparece «Libre» con «Claude frena · sigue con Codex». Con empate de nivel manda Claude. *Frena* solo aparece cuando todos los agentes activos frenan.
- Fichas por agente en Semáforo, Margen y Píldora («● Claude Frena  ● Codex Libre»); la Píldora nombra al agente y su detalle lista a todos. Los avisos de Windows y el tooltip de la bandeja nombran el agente.
- Las ventanas ahora tienen su propio nombre y duración: Codex con plan gratuito tiene una sola ventana de 30 días y se muestra como «Mes».

### Changed
- En Margen, una ventana sin uso dice «Sin uso · 0 % en 5 h» en vez de presumir un margen que solo es el tiempo transcurrido.
- Clásico sigue mostrando solo Claude.
- Los datos con más de 15 minutos siguen contando para el estado y se señalan como desactualizados (no generan avisos).

## [0.2.0] - 2026-10-23

### Added
- Avisos de Windows al cambiar de estado: al pasar a *Ojo*, al pasar a *Frena* y «Ya puedes seguir trabajando» cuando *Frena* termina. No avisa al arrancar, sin datos ni con datos desactualizados, y no repite el mismo aviso en 10 minutos.
- Más vida visual: al cambiar de estado la palabra y el color se funden con un pequeño deslizamiento y el borde da un destello; la luz de Semáforo y Píldora late despacio en *Ojo* y más rápido en *Frena* (queda quieta en *Libre*).
- Ajustes: interruptores «Animaciones» y «Avisos de Windows», y un botón «Probar aviso».

### Fixed
- Ajustes ya no falla al abrirlo por segunda vez tras cerrarlo (el programa seguía apuntando a la ventana borrada; el error quedaba en el log).

### Changed
- Las animaciones solo gastan CPU mientras hay algo que animar: se detienen si el widget está oculto en la bandeja y en estado *Libre*.

## [0.1.0] - 2026-10-23

### Added
- Cuatro estilos de widget que se eligen en el panel de opciones (fila **Estilo**) y se guardan: **Semáforo** (luz y palabra *Libre / Ojo / Frena*), **Margen** («Te sobra 1 h 02 min de margen»), **Píldora** (cápsula mínima que se despliega con anillos al pasar el ratón) y **Clásico** (el diseño anterior).
- El estado *Libre / Ojo / Frena* se calcula por ritmo: compara cuánto llevas gastado con el tiempo que ha pasado de la ventana, además de los umbrales de aviso.
- Opción «Opciones» en el menú de la bandeja.

### Changed
- Un único ejecutable en la raíz: `ClaudeWidget.pyw`. El código vive ahora en el paquete `claude_usage/`.
- Los umbrales de Ajustes pasan a llamarse «Ojo» y «Frena» (antes aviso amarillo y rojo).
- Las filas Vista y Tamaño del panel solo aparecen con el estilo Clásico.
- La opacidad y otros ajustes se guardan agrupados, no en cada paso del deslizador.
- Si el inicio con Windows estaba activado, el acceso directo se actualiza solo al nuevo lanzador.

### Removed
- La versión Tk de respaldo: ahora se necesita PySide6. Si falta, aparece un aviso de Windows con la instrucción de instalación en lugar de cambiar de interfaz en silencio.
- `instalar_inicio.ps1`: usa Ajustes → Iniciar con Windows.
- `widget.py`, `widget_qt.py` y `widget.pyw` (reemplazados por el paquete y `ClaudeWidget.pyw`).

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

