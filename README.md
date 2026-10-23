# Claude Usage Widget

**Versión 0.2.0 «Aurora»** · Desarrollado por **Pfruit99** con **Claude Code**

Widget de escritorio para Windows que responde de un vistazo a una pregunta: **¿puedo seguir trabajando con Claude Code?** Compara cuánto llevas gastado de los límites de 5 horas y semanal con el tiempo que ha pasado, y te lo dice como *Libre*, *Ojo* o *Frena*.

## Estilos

Se eligen en el panel de opciones (fila **Estilo**) y se guardan.

| Estilo | Qué muestra |
|--------|-------------|
| **Semáforo** | Luz de color y palabra grande, barra con marca de ritmo y hora de reinicio |
| **Margen** | El uso traducido a tiempo útil: «Te sobra 1 h 02 min de margen» |
| **Píldora** | Cápsula mínima (luz + estado + reinicio); al pasar el ratón se despliegan los anillos |
| **Clásico** | Anillos o barras, tamaño compacto o completo, con tokens y contexto |

**Cómo se decide el estado** (los umbrales se cambian en Ajustes):

- **Frena**: algún límite al 90 % o más, o agotado.
- **Ojo**: algún límite al 70 % o más, o vas más de 10 puntos por delante del tiempo transcurrido.
- **Libre**: el resto.

La marca blanca en barras y anillos indica cuánto deberías llevar según el tiempo transcurrido.

## Avisos y animaciones

**Avisos de Windows** (se desactivan en Ajustes; «Probar aviso» te enseña cómo se ven):

| Cambio | Aviso |
|--------|-------|
| *Libre* → *Ojo* | «Ojo con el uso» |
| Cualquiera → *Frena* | «Frena un momento», con la hora de reinicio |
| *Frena* termina | «Ya puedes seguir trabajando» |

No avisa al arrancar, sin datos ni con datos desactualizados, y no repite el mismo tipo de aviso en 10 minutos.

**Animaciones** (se desactivan en Ajustes → Animaciones): al cambiar de estado, la palabra y el color se funden y el borde da un destello; la luz de Semáforo y Píldora late despacio en *Ojo* y más rápido en *Frena*. Solo consumen mientras hay algo que animar.

## Cómo funciona

1. `statusline.ps1` lo ejecuta Claude Code como línea de estado y guarda los límites en `~\.claude\usage_limits.json`.
2. El widget lee ese archivo, cuenta los tokens de los logs en `~\.claude\projects\**\*.jsonl` y dibuja el estilo elegido.

## Requisitos

- Windows 10/11
- Python 3.10 o superior
- `pip install PySide6-Essentials`
- Claude Code con la línea de estado configurada

## Instalación y uso

### 1. Activar la línea de estado

En `~\.claude\settings.json` agrega (ajusta la ruta):

```json
{
  "statusLine": {
    "type": "command",
    "command": "powershell -NoProfile -File \"C:\\ruta\\al\\proyecto\\statusline.ps1\""
  }
}
```

Reinicia Claude Code y envía un mensaje: el archivo de límites se crea con la primera respuesta.

### 2. Abrir el widget (sin ventana de consola)

Doble clic en `ClaudeWidget.pyw`, o:

```powershell
pythonw ClaudeWidget.pyw
```

Para ver errores en consola usa `python ClaudeWidget.pyw`. Si falta PySide6 aparece un aviso con la instrucción de instalación.

### 3. Iniciar con Windows (opcional)

Desde **Ajustes → Iniciar con Windows**.

## Controles

| Acción | Resultado |
|--------|-----------|
| Arrastrar | Mueve el widget (la posición se guarda) |
| Clic derecho, o clic en ⚙ | Abre el panel de opciones |
| Doble clic (estilo Clásico) | Alterna entre tamaño completo y compacto |
| Clic en ↻ (Clásico completo) | Actualiza al instante |
| `R` / `Esc` en el panel | Actualizar / cerrar |

### Panel de opciones

Selectores con icono de un solo clic para **Estilo**, **Tema** (automático, claro u oscuro) y, solo con el estilo Clásico, **Vista** (anillos o barras) y **Tamaño**. Incluye **Ajustes…**, **Actualizar ahora** y **Salir**. Queda abierto, se mueve desde cualquier zona libre, recuerda su posición y se atenúa cuando el ratón no está encima.

### Ajustes

- **Apariencia:** tema, opacidad (30–100 %) y animaciones.
- **Datos:** intervalo de actualización (5, 15, 30 o 60 s) y umbrales de «Ojo» y «Frena» (por defecto 70 % y 90 %).
- **Sistema:** iniciar con Windows, avisos de Windows (con botón «Probar aviso») y restablecer valores.

Todo se aplica al instante y se guarda en `~\.claude-usage-widget.json`. Los valores fuera de rango vuelven al valor por defecto. Los errores se guardan en `~\.claude-usage-widget.log`.

## Estructura

| Ruta | Descripción |
|------|-------------|
| `ClaudeWidget.pyw` | Único ejecutable: lanzador sin consola |
| `statusline.ps1` | Línea de estado de Claude Code que escribe los límites (se queda en la raíz porque `settings.json` apunta a ella) |
| `claude_usage/` | Paquete: `config`, `limits`, `status` (Libre/Ojo/Frena), `alerts` (avisos), `texts`, `tokens`, `winsys`, `app` |
| `claude_usage/ui/` | Interfaz Qt: ventana, panel de opciones, ajustes, dibujo común y efectos (`fx`) |
| `claude_usage/ui/styles/` | Un módulo por estilo: `semaforo`, `margen`, `pildora`, `clasico` |
| `assets/icon.ico` | Icono (regenerable con `python ClaudeWidget.pyw --export-icon`) |
| `tests/` | Pruebas: `python -m unittest discover -s tests` |
| `docs/` | Notas de diseño y especificaciones |

### Añadir un estilo

Crea un módulo en `claude_usage/ui/styles/` con una clase con `layout(ctx) -> Layout` y `paint(p, ctx, layout)`, regístralo en `styles/__init__.py` y añade su entrada a `STYLE_CHOICES` en `config.py` y su icono en `Panel._icon`.
