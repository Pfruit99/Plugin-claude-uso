# Brainstorm: interfaz más fluida y ejecución sin ventana de terminal

## Oportunidad
- **Usuario**: quien tiene el widget abierto todo el día junto a Claude Code.
- **Resultado deseado**: que se vea nítido, se mueva sin tirones, no parpadee y arranque solo, sin ventana de consola.
- **Restricción**: seguir siendo liviano (solo biblioteca estándar, ~0 % CPU en reposo).

## Causas probables de la falta de fluidez (en el código actual)
| Causa | Efecto visible |
|-------|----------------|
| `draw()` hace `delete("all")` y recrea ~50 items | Parpadeo al redibujar (cada minuto o cambio) |
| Sin DPI awareness | Texto borroso en pantallas con escala 125-150 % (Windows lo estira) |
| Color transparente `-transparentcolor` | Bordes dentados en las esquinas redondeadas y los anillos (tkinter no tiene antialiasing) |
| Los valores saltan de golpe | El anillo/barra cambia sin transición |
| Arrastre con `geometry()` en cada evento | Puede ir a tirones si el redibujo coincide con el movimiento |
| `python widget.py` | Abre una consola que queda visible |

## Ideas

### Producto
1. Arranque automático con Windows, sin ventana ni intervención.
2. Icono en la bandeja del sistema (mostrar/ocultar, salir), para no depender de la ventana.
3. Recordar posición y asegurarse de que no quede fuera de pantalla si cambia el monitor.
4. Modo "se atenúa" (baja la opacidad) cuando el uso está bajo y se resalta al subir.
5. Versión portable: un solo acceso directo, sin instalar nada.

### Diseño
1. Transición suave (ease-out de ~250 ms) cuando cambia un porcentaje; sin animación en reposo.
2. Fuentes y trazos nítidos con DPI awareness.
3. Elementos fijos creados una sola vez (fondo, textos, pistas) y solo se actualizan los que cambian.
4. Aparición suave (fade-in) al abrir y al cambiar de vista.
5. Sombras o bordes sutiles que no dependan del color transparente.

### Ingeniería
1. **Lanzador sin consola**: `.pyw` + `pythonw.exe`, o un acceso directo / `.vbs` que lo ejecute oculto.
2. **DPI awareness** con `ctypes.windll.shcore.SetProcessDpiAwareness(1)`: una línea que mejora mucho la nitidez.
3. **Canvas en modo retenido**: crear items una vez y usar `itemconfig`/`coords`, en lugar de borrar todo.
4. **Registro de errores en archivo**: con `pythonw` no hay `stderr`; un fallo se vería como "el widget no abre". Un `widget.log` pequeño lo evita.
5. **Instancia única** (socket local o mutex) para que el arranque automático y el manual no dupliquen ventanas.

## Top 5 priorizado

| # | Idea | Por qué | Supuesto a validar |
|---|------|---------|--------------------|
| 1 | **Lanzador sin consola** (`.pyw` + acceso directo) | Es el pedido directo, cuesta minutos. | `pythonw`/`pyw` está en el PATH |
| 2 | **DPI awareness** | Mayor ganancia visual con una línea. | Tu pantalla usa escala > 100 % |
| 3 | **Canvas retenido (sin `delete("all")`)** | Elimina el parpadeo y reduce CPU. | El parpadeo se nota hoy; medir antes/después |
| 4 | **Log de errores + instancia única** | Hace seguro el arranque sin consola. | Ninguno relevante |
| 5 | **Transición suave de valores** | Da sensación de fluidez, solo corre al cambiar. | CPU durante 250 ms es aceptable (<5 %) |

### Opciones para ocultar la consola (comparación)
| Opción | Ventaja | Desventaja |
|--------|---------|------------|
| Renombrar a `widget.pyw` y abrir con doble clic | Cero archivos extra | Hay que apuntar los accesos directos a `.pyw` |
| Acceso directo a `pythonw.exe widget.py` | Simple, permite icono propio | Ruta absoluta al intérprete |
| `.vbs` que llama `pythonw` | Sin dependencias del PATH | Un archivo más |
| `.exe` con PyInstaller `--noconsole` | Sin Python instalado | ~10 MB, tarda en arrancar, posibles falsos positivos de antivirus |

**Recomendación**: acceso directo en la carpeta de Inicio apuntando a `pythonw.exe` (o a `pyw.exe`) + log de errores. PyInstaller solo si quieres compartirlo con alguien sin Python.

## Orden sugerido
1. DPI awareness + log de errores + instancia única.
2. Lanzador oculto y acceso directo de inicio.
3. Canvas retenido.
4. Transición de valores.
