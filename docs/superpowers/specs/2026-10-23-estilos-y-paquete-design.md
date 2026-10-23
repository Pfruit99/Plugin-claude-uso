# Estilos de widget y paquete con un solo ejecutable — diseño

Fecha: 2026-10-23 · Base: v0.0.5 «Aurora» (copia en la rama `backup/v0.0.5-aurora` y en `Documents/claude-usage-widget-v0.0.5-backup.zip`)

## Intención y el porqué

Quien usa el widget lo mira para decidir **si puede seguir trabajando con Claude**. Hoy muestra porcentajes y el usuario tiene que interpretarlos. El widget debe responder la pregunta directamente (*Libre / Ojo / Frena*) y dejar las cifras como detalle.

Además, el proyecto tiene tres puntos de entrada (`widget.pyw`, `widget.py`, `widget_qt.py`), una interfaz Tk duplicada y la lógica mezclada con el dibujo. Se reorganiza para que la raíz tenga **un solo ejecutable**.

## Objetivos

1. Cuatro estilos elegibles desde el panel de opciones, que se aplican al instante y se guardan:
   - **Semáforo**: luz de color + palabra grande + barra con marca de ritmo + hora de reinicio.
   - **Margen**: frase en tiempo útil («Te sobra 1 h 02 min de margen») + una barra con marca «ahora» + línea de la semana.
   - **Píldora**: píldora mínima (luz + estado + reinicio) que al pasar el ratón se despliega con los anillos.
   - **Clásico**: el diseño actual (anillos/barras, compacto/completo), sin pérdida de funciones.
2. Un estado calculado por **ritmo** (uso frente a tiempo transcurrido), no solo por porcentaje.
3. Un único ejecutable en la raíz: `ClaudeWidget.pyw`. El resto vive en el paquete `claude_usage/`.
4. Lógica separada del dibujo y con pruebas automáticas.

## No-objetivos

- Compilar un `.exe` (se deja la estructura preparada, no se hace).
- Avisos de Windows, historial/sparkline, atajo global (ideas posteriores).
- Cambiar el formato de `usage_limits.json` ni el funcionamiento de `statusline.ps1`.
- Mantener la interfaz Tk.

## Anti-objetivos (fracaso aunque funcione)

- Subir el consumo en reposo: se mantiene «solo redibuja cuando cambia algo».
- Perder el acceso a las cifras exactas (el porcentaje debe verse en los 4 estilos, aunque sea en segundo plano).
- Que quien ya tenía el widget en el inicio de Windows se quede sin él tras actualizar.

## Restricciones

- Windows 10/11, Python 3.10+, PySide6 (`PySide6-Essentials`). Sin otras dependencias nuevas en producción (`pytest` solo para desarrollo).
- Configuración en `~\.claude-usage-widget.json`, compatible hacia atrás: las claves nuevas tienen valor por defecto.
- `statusline.ps1` se queda en la raíz: `settings.json` del usuario apunta a esa ruta.

## Approaches considerados

| # | Enfoque | Compensación |
|---|---------|--------------|
| 1 | Paquete `claude_usage/` + un lanzador `ClaudeWidget.pyw` | Sin compilar; necesita Python instalado |
| 2 | `.exe` con PyInstaller | No necesita Python; 60–100 MB, falsos positivos del antivirus, paso de compilación |
| 3 | Paquete + lanzador + script que genera el `.exe` | Lo mejor de ambos; más trabajo ahora |

**Elegido por el usuario: 1.** La estructura (paquete con `main()` en `app.py`) deja la 3 a un paso.

## Diseño

### Estructura

```
ClaudeWidget.pyw            único ejecutable de la raíz
statusline.ps1              se queda: la referencia settings.json del usuario
assets/icon.ico
claude_usage/
  __init__.py               VERSION, CODENAME, AUTHOR, APP_NAME
  app.py                    main(): logging, instancia única, QApplication, bandeja
  config.py                 DEFAULT_CONFIG, sanitize, load/save
  limits.py                 read_limits() -> Limits (dataclass)
  tokens.py                 TokenCounter
  status.py                 compute_status(limits, cfg, now) -> Status        (puro)
  formatting.py             fmt_duration, fmt_remaining, fmt_ago, fmt_tokens
  winsys.py                 tema de Windows, inicio con Windows, DPI, mutex, log
  ui/
    theme.py, fonts.py, icon.py
    card.py                 ventana flotante: datos, animación, eventos
    panel.py                panel de opciones
    settings.py             ventana de Ajustes
    styles/
      __init__.py           STYLES = {"semaforo": ..., "margen": ..., "pildora": ..., "clasico": ...}
      base.py               protocolo Style y Layout
      semaforo.py margen.py pildora.py clasico.py
tests/                      pytest: status, config, formatting, tokens, layouts
```

Se eliminan `widget.py`, `widget_qt.py`, `widget.pyw` e `instalar_inicio.ps1`.

### Patrón de estilos (strategy sencillo)

Cada estilo es un objeto con dos operaciones, sin herencia profunda:

- `layout(ctx) -> Layout`: tamaño de la tarjeta y lista de zonas clicables `(rect, acción)`.
- `paint(painter, ctx, layout)`: dibuja usando **ese mismo** `Layout`.

`Card` elige el estilo con `STYLES[cfg["style"]]`. Así el dibujo y los clics comparten una sola fuente de coordenadas (hoy están duplicadas en `_height()` y `mouseReleaseEvent`). `ctx` es un `Snapshot` inmutable con límites, tokens, estado, valores animados, configuración, paleta, fuentes y si el ratón está encima. Los estilos no tocan archivos ni configuración.

### Estado (`status.py`, función pura)

Para cada ventana (5 h y semanal): `uso = pct/100`, `ritmo = fracción de tiempo transcurrida` (desconocida si no hay hora de reinicio).

- **Frena**: algún pct ≥ `bad` (90 por defecto), o límite agotado (≥ 100).
- **Ojo**: algún pct ≥ `warn` (70), o `uso > ritmo + 0.10`.
- **Libre**: el resto.
- **Sin datos**: no hay ninguna ventana.

El estado global es el peor de las dos ventanas. `Status` incluye: nivel, ventana que lo decide, `margen_segundos = (ritmo − uso) × duración_ventana` (negativo = vas por delante) y tiempo hasta el reinicio. Las frases del estilo Margen salen de ahí («Te sobra X de margen» / «Vas X por delante» / «Vuelve en X»).

### Opciones y configuración

- Clave nueva `style` (`semaforo` por defecto). Se valida en `sanitize_config`.
- Panel de opciones: nueva fila **Estilo** con 4 iconos. Las filas **Vista** y **Tamaño** solo aparecen con Clásico; **Tema** y las acciones no cambian.
- Ajustes: sin cambios, salvo que los umbrales `warn`/`bad` también definen el estado.

### Lanzador y errores

`ClaudeWidget.pyw` solo llama a `claude_usage.app.main()`. Si falta PySide6 muestra un `MessageBox` de Windows con la instrucción de instalación y escribe el error en el log. Ya no hay caída silenciosa a otra interfaz.

### Inicio con Windows

`set_startup` apunta a `ClaudeWidget.pyw`. Al arrancar, si el acceso directo de Inicio existe se **recrea siempre** (idempotente), de forma que el atajo antiguo que apuntaba a `widget.pyw` queda migrado sin pasos manuales.

### Pruebas

`pytest` sobre: `compute_status` (umbrales, ritmo desconocido, límite agotado), `sanitize_config`, formateadores, `TokenCounter` (lectura incremental) y `layout()` de cada estilo (tamaños y zonas dentro de la tarjeta). El dibujo en sí se revisa a mano.

## Decisiones mías (no confirmadas por el usuario)

- Estilo por defecto: Semáforo (también para quien actualiza).
- Eliminar la versión Tk completa y `instalar_inicio.ps1` (duplicado de `set_startup`).
- Tolerancia de ritmo de 10 puntos para pasar a *Ojo*.
- `statusline.ps1` se queda en la raíz como excepción al «un solo ejecutable».
- Vista/Tamaño solo visibles en Clásico.
- Versión nueva: 0.1.0 (cambio de estructura); entrada en `CHANGELOG.md` bajo *Unreleased* durante el trabajo.

## Se deja al constructor

- Pixel exacto, espaciados, animaciones y colores de cada estilo (guiados por los mockups aprobados).
- Cómo evitar parpadeo en la Píldora al desplegarse (retardo de cierre, ancla superior izquierda).
- Orden de migración del código por commits y detalles de nombres internos.
- Actualizar `README.md` (estructura, uso, requisitos).
