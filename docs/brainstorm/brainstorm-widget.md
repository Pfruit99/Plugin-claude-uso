# Brainstorm: interfaz, arquitectura y buenas prácticas del widget de uso de Claude

## 1. Qué es hoy
- `statusline.ps1`: Claude Code lo ejecuta en cada actualización de la línea de estado. Escribe `~/.claude/usage_limits.json` (5 h, semanal, contexto).
- `widget.py`: ventana tkinter sin bordes, siempre encima. Lee ese JSON cada 5 s y cuenta tokens de los logs `.jsonl` cada 30 s. Dibuja todo en un `Canvas`.
- Sin dependencias externas. Es un buen punto de partida, y la meta es mantenerlo así.

**Usuario**: quien usa Claude Code (plan Pro/Max) y quiere ver de un vistazo cuánto límite le queda, sin abrir nada.
**Función central**: responder "¿me alcanza para seguir trabajando y cuándo se reinicia?" en menos de 1 segundo de mirada.

## 2. Problemas detectados en el código actual (corregir primero)
| # | Dónde | Problema | Arreglo |
|---|-------|----------|---------|
| 1 | `widget.py:227` | "Actualizar ahora" llama `refresh()` con `reschedule=True`. Cada clic crea **otra cadena de timers**, así que el widget se refresca cada vez más seguido. | `command=lambda: self.refresh(reschedule=False)` |
| 2 | `statusline.ps1:15` | `Get-Date -UFormat %s` en Windows PowerShell 5.1 devuelve la hora local como si fuera UTC. `fmt_ago` y `STALE_SECONDS` quedan desfasados por la zona horaria. | `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` |
| 3 | `widget.py:46` | `windows_theme()` abre el registro en **cada** `draw()`. | Leerlo cada ~30 s o cachearlo. |
| 4 | `widget.py:307` | `draw()` borra y recrea ~50 items del canvas cada 5 s aunque nada cambió. | Calcular una "firma" de estado y redibujar solo si cambia. |
| 5 | `widget.py:125` | Si un `.jsonl` crece, se **vuelve a leer entero**. Esas sesiones pueden pesar MBs. | Leer incremental desde el último offset. |
| 6 | `widget.py:156` | `rglob` + `stat` de todos los logs cada 30 s, y `_cache` nunca elimina archivos viejos. | Podar el cache y guardar `epoch` ya parseado (no `fromisoformat` por fila en cada ciclo). |
| 7 | `statusline.ps1` | Arranca un proceso PowerShell (~200-500 ms) en cada refresco de la línea de estado y reescribe el JSON aunque no haya cambios. | Escribir solo si cambió un valor; o mover la lógica a un `statusline.py` pequeño. |
| 8 | `widget.py:317` | La etiqueta "Claude Pro" está fija. | Derivarla de config o quitarla. |

## 3. Ideas desde tres perspectivas

### Producto (valor)
1. **Alerta al cruzar 70 % / 90 %**: el borde del widget pulsa una vez, o aparece un aviso discreto. Es el momento de mayor valor.
2. **Ritmo de consumo ("burn rate")**: "a este ritmo se agota en 1 h 20 min". Responde si alcanza, algo que el porcentaje solo no dice.
3. **Modo mini-píldora**: una línea `5h 42% · 7d 18%` de ~200×28 px que se puede dejar en un borde de la pantalla.
4. **Umbrales configurables** (hoy 70/90 fijos) y opción de ocultar "Hoy/Semana/Contexto".
5. **Historial ligero**: sparkline de las últimas 24 h del % de 5 h, guardado en un `.csv` rotativo de pocos KB.

### Diseño (experiencia)
1. **Un solo mensaje dominante por estado**: normal = números; en riesgo = tiempo restante en grande; agotado = "Vuelve en X" en grande. Hoy todo pesa lo mismo.
2. **No depender solo del color**: añadir icono o texto (`●` `▲` `■`) para daltonismo y para el modo "anillo" pequeño.
3. **Atenuar datos viejos**: si `updated` supera 15 min, bajar la opacidad de los números y mostrar "datos de hace X", en lugar de solo pintar el reloj de naranja.
4. **Menos modos**: 2 vistas × 2 tamaños × 3 temas son 12 combinaciones que probar. Conviene dejar una vista principal bien cuidada y una compacta.
5. **Descubribilidad**: el menú contextual y el doble clic no se ven. Una pista de una sola vez ("clic derecho: opciones") o un tooltip.

### Ingeniería (liviano y robusto)
1. **Redibujo condicional + `after` único** (problemas 1, 3, 4). Con esto el widget queda casi a 0 % de CPU en reposo.
2. **Lectura incremental de logs** con offset por archivo, solo de archivos modificados en las últimas 24 h y 7 d. Evita reescanear todo.
3. **Una sola fuente de verdad**: que `statusline` guarde también los tokens y el widget solo lea un JSON, sin recorrer logs. Es lo más liviano, aunque depende de lo que exponga Claude Code.
4. **Instancia única** (mutex o archivo de bloqueo) y arranque con `pythonw.exe` para que no haya consola.
5. **Pruebas pequeñas** de las funciones puras (`fmt_duration`, `read_limits`, `level_color`, conteo de tokens) con `pytest`/`unittest`. Hoy están bien separadas, así que es barato.

## 4. Top 5 priorizado (valor × rapidez de validar × diferenciación)

| Prioridad | Idea | Por qué | Supuesto a validar |
|-----------|------|---------|--------------------|
| 1 | **Arreglar los bugs 1, 2, 3 y 4** | Sin ellos el widget no es fiable (hora mal, timers duplicados). Cuesta minutos. | Que el desfase de hora realmente ocurre en tu PowerShell (`powershell -c "Get-Date -UFormat %s"` vs `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`). |
| 2 | **Redibujo condicional + cache de tema** | Cumple "liviano" directamente. Se mide con el Administrador de tareas. | CPU en reposo < 0,5 %. |
| 3 | **Lectura incremental de logs + poda de cache** | Es el mayor costo escondido a medida que crecen los logs. | Tiempo de `totals()` con tus logs reales (medir con `time.perf_counter`). |
| 4 | **Alerta al 70/90 % + ritmo de consumo** | Es lo que convierte el widget de "tablero" en "herramienta que avisa". | Que prefieres un aviso a mirarlo; probar una semana. |
| 5 | **Estados visuales claros (agotado / riesgo / datos viejos) sin depender del color** | Mejora la lectura rápida sin añadir código pesado. | Que reconoces el estado en < 1 s a 1 m de distancia. |

## 5. Buenas prácticas por capa

**Arquitectura**
- Separar tres capas, aunque sigan en un archivo o en tres módulos pequeños: `data` (leer JSON y logs), `model` (formatear, calcular niveles) y `view` (canvas). Hoy `Widget` mezcla estado, I/O y dibujo.
- Mantener la dependencia solo de la biblioteca estándar. Es la principal razón por la que el widget es liviano.
- Contrato claro del JSON (`five_hour`, `seven_day`, `context`, `updated`) y versión (`"v": 1`) para que statusline y widget evolucionen sin romperse.
- Escritura atómica (`.tmp` + `Move-Item`) ya está bien; conservarla.

**Diseño**
- Tokens de diseño centralizados (colores, fuentes, espaciados) en un diccionario, en lugar de números sueltos (`y + 82`, `y + 134`).
- Jerarquía: un número grande por ventana, texto secundario pequeño, todo lo demás oculto o en el menú.
- Contraste mínimo 4,5:1 en ambos temas; revisar `muted="#888780"` sobre blanco (queda justo).

**Código**
- Hilo de fondo solo para I/O; la UI solo se toca desde el hilo principal (ya lo haces con `root.after(0, ...)`; mantenerlo).
- Capturar errores concretos (`OSError`, `ValueError`) como ya haces; no usar `except:` genérico.
- Reducir la duplicación entre `_bar_full`/`_bar_compact` y `_ring` con una función de "datos de ventana" (pct, color, texto) que las vistas solo dibujen.
- Fuentes: `Segoe UI` es correcta en Windows; fijar un fallback para evitar saltos de tamaño.
- Medir antes de optimizar: CPU, RAM (`~25-35 MB` es normal para tkinter) y tiempo de `totals()`.

## 6. Orden de trabajo sugerido
1. Bugs 1 y 2 (10 min).
2. Cache de tema y redibujo condicional (30 min).
3. Lectura incremental de logs (1 h).
4. Alertas y ritmo de consumo (2-3 h).
5. Pruebas unitarias de funciones puras y refactor en capas.
