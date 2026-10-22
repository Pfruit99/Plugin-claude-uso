# Brainstorm: datos estáticos vs dinámicos y menú gráfico

## 1. Qué datos de la interfaz son estáticos y cuáles cambian

### Estáticos (fijos en el código, no cambian mientras corre)
| Dato | Dónde | Valor |
|------|-------|-------|
| Títulos y etiquetas | `draw`, `_bar_*`, `_ring` | "Uso de Claude", "Claude", "Ventana de 5 horas", "Semanal", "5 h", "Semana", "Hoy", "Contexto" |
| Mensajes de estado | `draw` | "Límite de 5 h agotado", "Sin datos de límites…", "Vuelve en…", "Se reinicia en…" |
| Paleta de colores | `THEMES`, `OK/WARN/BAD` | claro y oscuro, tres colores de nivel |
| Medidas y fuentes | `PAD`, `WIDTHS` (290/330), radios, grosores, `Segoe UI` | todo en píxeles lógicos |
| Posiciones verticales | `_bars`, `_rings` | `y + 12`, `y + 82`, etc. |
| Tiempos | `STALE_SECONDS` (15 min), `TOKENS_EVERY` (30 s), `ANIM_MS` | constantes |
| Glifos | `↻`, `⚙`, `⚠` | texto, no iconos |
| Textos del menú | `_build_menu` | "Vista", "Tamaño", "Tema", "Ajustes…", "Actualizar ahora", "Salir" |

### Configurables (cambian solo si el usuario los toca, se guardan en el JSON)
`view`, `size`, `theme`, `topmost`, `refresh`, `warn`, `bad`, `opacity`, `x`, `y`.

### Dinámicos (cambian solos mientras el widget corre)
| Dato | Fuente | Frecuencia |
|------|--------|-----------|
| % de la ventana de 5 h y semanal | `usage_limits.json` (statusline) | cada `refresh` s |
| Cuenta atrás "se reinicia en…" | `resets_at` − hora actual | cada minuto |
| "↻ hace X min" | `updated` | cada minuto |
| Tokens Hoy / Semana | logs `.jsonl` | cada ≥ 30 s |
| Contexto % | `usage_limits.json` | cada `refresh` s |
| Tema efectivo (si es "auto") | registro de Windows | cada 30 s |
| Estado: datos viejos, agotado | derivado de lo anterior | en cada dibujo |
| Valor animado del anillo/barra | `_shown` | ~60 fps solo mientras cambia |
| Engranaje al pasar el mouse | `_hover` | por evento |

**Conclusión**: ~80 % de lo que se ve es fijo. Lo realmente vivo son 6 valores: 2 porcentajes, 2 cuentas atrás, tokens y contexto. Eso confirma que el redibujo condicional (solo cuando cambia la firma) es lo correcto, y que los textos fijos podrían ir en una sola tabla (`TEXTOS`) para facilitar cambiarlos o traducirlos.

## 2. Menú gráfico: cómo mostrar Vista, Tamaño, Tema, Ajustes, Actualizar ahora y Salir

Hoy es el menú nativo de Windows (`tk.Menu`): texto plano, submenús anidados, sin iconos, sin relación con el tema claro/oscuro del widget y con 2 clics para cambiar una opción.

### Ideas

**Producto**
1. Cambiar de vista, tamaño o tema en **un solo clic** (sin submenús).
2. Mostrar el **estado actual** de cada opción de un vistazo (cuál está activa).
3. Acciones frecuentes ("Actualizar", "Salir") separadas de las preferencias.
4. Atajos visibles (por ejemplo `R` para actualizar, `Esc` para cerrar).
5. Coherencia: el menú adopta el tema del widget (claro/oscuro/opacidad).

**Diseño**
1. **Panel flotante propio** con **selectores segmentados** con icono: Vista `◔ | ▬`, Tamaño `▭ | ▣`, Tema `A | ☀ | ☾`.
2. Filas de acción con icono: `⚙ Ajustes`, `↻ Actualizar ahora`, `✕ Salir` (Salir en rojo suave).
3. Resaltar la opción activa con el color de acento y un fondo sutil; hover claro.
4. Esquinas redondeadas, misma tipografía y paleta que el widget; aparece junto al engranaje.
5. Mini-vista previa: el icono de Vista dibuja un anillo o una barra diminuta, no solo texto.

**Ingeniería**
1. **`Toplevel` sin borde (`overrideredirect`) con `tk.Canvas` o `tk.Label`/`Frame`**, dibujado con la misma paleta (`THEMES`) y escala (`self.S`).
2. Cierre al perder el foco (`<FocusOut>`), al hacer clic fuera o con `Esc`.
3. **Opciones definidas en una tabla** (clave, icono, etiqueta, valores) para generar tanto el panel como la ventana de Ajustes (no duplicar).
4. Iconos como **glifos de fuente** (`Segoe UI Symbol` / `Segoe MDL2 Assets`): sin archivos de imagen, sin dependencias.
5. Crear el panel bajo demanda y destruirlo al cerrar (cero costo en reposo).

### Opciones de implementación
| Opción | Aspecto | Esfuerzo | Peso | Riesgo |
|--------|---------|----------|------|--------|
| Menú nativo actual | Básico | 0 | 0 | Ninguno |
| Panel `Toplevel` sin borde con segmentos e iconos (glifos) | Moderno, coherente con el widget | Medio | Bajo | Foco y cierre |
| Dibujar el menú **dentro del propio canvas** como overlay | Muy integrado | Medio-alto | Bajo | Ventana limitada al tamaño del widget; el compacto no cabe |
| Barra de iconos horizontal al pasar el mouse | Rápido y visual | Bajo | Bajo | Sin etiquetas, menos claro |
| Librería externa (customtkinter, PySide) | Muy pulido | Alto | Alto (20-100 MB) | Rompe "liviano" |

## 3. Top 5 priorizado

| # | Idea | Por qué | Supuesto a validar |
|---|------|---------|--------------------|
| 1 | **Panel flotante con selectores segmentados con icono** (reemplaza submenús) | Un clic por cambio y estado visible; es el pedido central. | Que caben 3 selectores + 3 acciones en ~220 px de ancho |
| 2 | **Panel con el tema y la escala del widget** | Coherencia visual, sin costo extra (ya existen `THEMES` y `self.S`). | Que el contraste es suficiente en ambos temas |
| 3 | **Cierre por foco, clic fuera y `Esc`** | Sin esto el panel molesta; es la parte más frágil. | Que `FocusOut` funciona con ventanas sin borde en Windows |
| 4 | **Tabla única de opciones** (panel + ajustes) | Evita código duplicado y errores al añadir opciones. | Que ≥ 8 opciones justifican la tabla |
| 5 | **Textos fijos en una tabla `TEXTOS`** | Lo estático (~80 %) queda en un solo sitio, listo para traducir. | Que nadie lo necesita en otro idioma hoy (entonces es opcional) |

## 4. Esbozo del panel

```
┌──────────────────────────┐
│ Vista     [ ◔ ] [ ▬ ]    │   ← activo resaltado
│ Tamaño    [ ▭ ] [ ▣ ]    │
│ Tema      [ A ] [ ☀ ] [ ☾ ]│
├──────────────────────────┤
│ ⚙  Ajustes…              │
│ ↻  Actualizar ahora   R  │
│ ✕  Salir                 │
└──────────────────────────┘
```

## 5. Orden sugerido
1. Extraer las opciones y textos a tablas (`OPCIONES`, `TEXTOS`).
2. Panel `Toplevel` sin borde con la paleta del widget y filas de acción.
3. Selectores segmentados con glifos y estado activo.
4. Cierre por foco / clic fuera / `Esc`, y posición junto al engranaje sin salirse de pantalla.
5. Mantener el menú nativo como respaldo si el panel falla.
