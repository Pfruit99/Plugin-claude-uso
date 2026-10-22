# Brainstorm: mejorar el aspecto gráfico sin gastar RAM

## 1. Diagnóstico del estado actual (`widget.py`)

| Área | Hoy | Límite visual |
|------|-----|---------------|
| Motor | `tkinter.Canvas`, solo stdlib | Sin antialiasing: arcos y óvalos con bordes dentados |
| Transparencia | `-transparentcolor #010203` (color clave) | Esquinas redondeadas con "halo" oscuro/claro; sin sombra ni translucidez real |
| Anillos | `create_arc` de un solo color + dos óvalos como tapa | Sin degradado, sin brillo, sin marca de ritmo |
| Iconos | Glifos de texto (`⚙ ↻ ⚠ ☀ ☾`) | Dependen de la fuente, se ven como "emoji", no como iconos Fluent |
| Tipografía | Segoe UI / Segoe UI Semibold | Correcta, pero sin jerarquía fuerte (número grande vs. etiqueta) |
| Color | Paleta fija + acento `#D97757` | No sigue el color de acento de Windows |
| Datos | Solo valor actual | Sin historial: no se ve la tendencia |
| Animación | Easing 0,22 a ~60 fps solo al cambiar | Bien para RAM; faltan micro-transiciones (hover, cambio de tema) |

Lo bueno que se debe conservar: redibujo por firma (`sig`), conteo incremental de logs, panel creado bajo demanda, cero dependencias.

## 2. Ideas por perspectiva

### Product Manager
1. **Marca de ritmo** en anillo/barra: una muesca que indica cuánto "deberías" llevar según el tiempo transcurrido de la ventana. Convierte el % en una decisión ("voy rápido / voy bien").
2. **Mini-historial (sparkline)** de uso de las últimas 24 h y 7 días.
3. **Icono de bandeja con el %** y modo "solo bandeja": el widget aparece al pasar el mouse.
4. **Presets de estilo** (Claude coral, Cristal, Terminal, Alto contraste) en un clic.
5. **Alertas visuales** al cruzar umbrales: pulso suave y notificación toast de Windows una sola vez.

### Product Designer
1. **Anillos con degradado** (verde → ámbar → rojo a lo largo del arco) y tapa redondeada con leve brillo.
2. **Fondo Mica / acrílico** y esquinas nativas de Windows 11, con sombra suave en lugar del color clave.
3. **Iconos Segoe Fluent Icons** (o Segoe MDL2 en Win10) en vez de emoji, con grosor uniforme.
4. **Jerarquía tipográfica**: porcentaje grande en *Segoe UI Variable Display*, etiquetas pequeñas en mayúsculas con tracking, cifras tabulares.
5. **Color de acento del sistema** (registro `AccentColor`) y transiciones suaves al cambiar de tema, hover y estado.

### Software Engineer
1. **Render supersampleado con Pillow** (dibujar a 3x y reducir) y mostrar la imagen: antialiasing real, degradados y glow por unos 8–12 MB más.
2. **Ventana en capas con alfa por píxel** (`UpdateLayeredWindow` vía `ctypes`): sombra suave y bordes perfectos, sin color clave.
3. **DWM por `ctypes`**: `DWMWA_WINDOW_CORNER_PREFERENCE`, `DWMWA_SYSTEMBACKDROP_TYPE` (Mica/Acrílico) y modo oscuro de la barra. Coste de RAM: cero.
4. **Caché de fotogramas estáticos**: fondo, pista y etiquetas se renderizan una vez; solo se recompone el arco. Menos CPU y sin crecimiento de memoria.
5. **Recorte del working set** tras cada redibujo (`SetProcessWorkingSetSize(-1,-1)`) y animación a 30 fps con batería/pantalla completa: baja la RAM que ve el Administrador de tareas.

## 3. Top 5 priorizado

| # | Idea | Por qué | RAM extra | Supuesto a validar |
|---|------|---------|-----------|--------------------|
| 1 | **DWM: esquinas, sombra y Mica** (E3 + D2) | Mayor salto visual con coste cero; quita el halo del color clave | ~0 MB | Que funcione con `overrideredirect`; si no, usar `WS_POPUP` + `SetWindowLong` |
| 2 | **Anillos con degradado y antialiasing (Pillow, 3x)** (E1 + D1) | Es lo más visible del widget y hoy lo más tosco | +8–12 MB | Que el total siga bajo ~45 MB y el redibujo < 5 ms |
| 3 | **Marca de ritmo + sparkline** (PM1 + PM2) | Convierte el adorno en información útil; diferencia frente a la línea de estado | ~0,5 MB (buffer de muestras) | Que el usuario entiende la muesca sin leyenda |
| 4 | **Tipografía + iconos Fluent + acento del sistema** (D3 + D4 + D5) | Percepción de "app nativa" sin dependencias | ~0 MB | Que Segoe Fluent Icons exista (Win11); en Win10 caer a MDL2 |
| 5 | **Icono de bandeja con %** (PM3) | Visible aunque el widget esté oculto; menos pantalla ocupada | +5 MB (`pystray`) o 0 con `Shell_NotifyIcon` vía `ctypes` | Que el icono dinámico de 16 px se lee bien |

Orden recomendado: 1 → 4 → 2 → 3 → 5 (de menor a mayor coste de RAM, midiendo en cada paso).

## 4. Qué se necesitaría (programas)

| Necesidad | Programa / paquete | Obligatorio | Peso |
|-----------|--------------------|-------------|------|
| Ejecutar el widget | Python 3.10+ con tkinter (ya lo usas) | Sí | — |
| Antialiasing, degradados, sombra | `pip install pillow` | Para idea 2 | ~10 MB en RAM |
| Icono de bandeja | `pip install pystray` (o `ctypes` puro) | Opcional | ~5 MB |
| Mockups de estilos antes de programar | Figma o Canva (ya tienes conectores) | Opcional | — |
| Medir memoria | Administrador de tareas → "Conjunto de trabajo privado", o Process Explorer; `tracemalloc` en Python | Recomendado | — |
| Empaquetar sin Python instalado | PyInstaller o Nuitka | Opcional | Disco, no RAM |

### Alternativas de motor (referencia de RAM aproximada, a medir)
| Motor | RAM típica | Veredicto |
|-------|-----------|-----------|
| Tk actual | 20–30 MB | Base actual |
| Tk + DWM + Pillow | 30–45 MB | **Recomendado** |
| Win32 + Pillow sin Tk | 25–35 MB | Más ligero, más código |
| Rust nativo (Direct2D / tiny-skia) | 5–15 MB | Lo mejor en RAM; reescritura completa; requiere Rust + Build Tools |
| .NET WPF | 40–60 MB | Bonito, más pesado |
| PySide6 / Qt | 80–120 MB | Descartado |
| Tauri / WebView2 | 80–150 MB | Descartado |
| Electron | 150–300 MB | Descartado |

## 5. Reglas para no subir la RAM
1. Renderizar solo cuando cambia la firma (ya existe) y a tamaño fijo; reutilizar el mismo `PhotoImage`.
2. No guardar imágenes por fotograma: una caché con el fondo y otra con el arco.
3. Importar Pillow de forma diferida solo si el modo "HD" está activo, con interruptor en Ajustes.
4. Historial en un `array`/lista acotada (p. ej. 1 muestra/min × 7 días ≈ 10 080 puntos).
5. Medir antes y después de cada cambio; presupuesto: **< 45 MB** de conjunto de trabajo privado.
