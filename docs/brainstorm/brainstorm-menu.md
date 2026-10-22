# Brainstorm: menú de opciones del widget

## Oportunidad
- **Usuario**: quien deja el widget abierto todo el día y lo ajusta pocas veces (al instalarlo, al cambiar de monitor o de tema).
- **Hoy**: menú contextual de clic derecho con 3 submenús (Vista, Tamaño, Tema), "Siempre encima", "Actualizar ahora" y "Salir". Está poco descubrible (nada indica que existe) y las opciones nuevas (intervalo de refresco, umbrales, arranque con Windows) solo se cambian en el código.
- **Restricción**: tkinter, sin dependencias, poca memoria. El menú no debe añadir peso al widget cuando está cerrado.

## Qué opciones merecen estar en el menú
| Opción | Tipo | Frecuencia de uso | Dónde |
|--------|------|-------------------|-------|
| Vista (anillos/barras) | elegir 1 | media | menú rápido |
| Tamaño (compacto/completo) | elegir 1 | media | menú rápido (+ doble clic) |
| Siempre encima | interruptor | media | menú rápido |
| Tema (auto/claro/oscuro) | elegir 1 | baja | menú rápido o ajustes |
| Intervalo de refresco (5/15/30/60 s) | elegir 1 | baja | ajustes |
| Umbrales de aviso (70/90 %) | número | muy baja | ajustes |
| Opacidad | deslizador | baja | ajustes |
| Iniciar con Windows | interruptor | muy baja | ajustes |
| Restablecer posición | acción | muy baja | ajustes |
| Salir | acción | baja | menú rápido |

Regla: lo que se usa varias veces por semana va en el menú rápido; el resto, en una ventana de ajustes aparte.

## Ideas

### Producto
1. **Dos niveles**: menú rápido (5-6 entradas) + "Ajustes…" para lo avanzado. Evita un menú largo.
2. **Valores por defecto sensatos y botón "Restablecer"**: nadie tiene miedo de tocar.
3. **Cambios en vivo**: cada opción se aplica al instante, sin "Aceptar/Cancelar".
4. **Perfiles** ("trabajo" compacto y translúcido, "revisión" completo): una sola acción cambia varias opciones.
5. **Mostrar la versión y ruta de config/log** en "Acerca de", útil para soporte.

### Diseño
1. **Pista de descubrimiento**: engranaje ⚙ visible al pasar el mouse sobre el widget (hoy solo en compacto), en vez de depender del clic derecho.
2. **Marcas claras de estado** (✓ / ●) y texto corto: "Anillos", "Barras"; evitar frases largas.
3. **Panel de ajustes con secciones** (Apariencia, Datos, Sistema), no una lista plana.
4. **Vista previa inmediata**: el propio widget cambia mientras se mueve el deslizador de opacidad o se cambia el tema.
5. **Atajos y accesibilidad**: foco con teclado, `Esc` cierra, texto con contraste suficiente en ambos temas.

### Ingeniería
1. **Menú declarativo**: una tabla de opciones (clave, etiqueta, tipo, valores, callback) que genera tanto el menú rápido como la ventana de ajustes. Añadir una opción = una línea.
2. **Ventana de ajustes con `Toplevel` creada bajo demanda y destruida al cerrar**, para no consumir memoria cuando no se usa. Reutilizar widgets `ttk` (nativos, ligeros).
3. **Validación y config versionada**: rangos (intervalo 5-300 s, umbrales 1-100), claves desconocidas ignoradas, `"v": 1` para migraciones.
4. **Leer los valores desde la config en cada ciclo** (`REFRESH_MS`, `TOKENS_EVERY`, umbrales) en vez de constantes, para que el cambio sea inmediato sin reiniciar.
5. **Iniciar con Windows**: crear/borrar el acceso directo de Inicio desde la ventana de ajustes (hoy es un script aparte).

## Top 5 priorizado
| # | Idea | Por qué | Supuesto a validar |
|---|------|---------|--------------------|
| 1 | **Menú declarativo** (tabla de opciones) | Base de todo lo demás; evita duplicar código al añadir opciones. | Que habrá más de 8 opciones a medio plazo |
| 2 | **Dos niveles: menú rápido + "Ajustes…"** | Resuelve el menú largo y mantiene el clic derecho ágil. | Que 5-6 entradas cubren el 90 % del uso |
| 3 | **Valores en config y aplicados en vivo** (intervalo, umbrales, opacidad) | Es lo que la gente quiere tocar sin editar código. | Que `after` toma el nuevo intervalo sin reinicio |
| 4 | **Engranaje visible al pasar el mouse** | Descubribilidad: hoy el menú es invisible. | Que no estorba al diseño del widget |
| 5 | **Ventana de ajustes bajo demanda con ttk + "Restablecer"** | Aloja lo avanzado sin costo en memoria. | Memoria extra < 5 MB y se libera al cerrar |

## Opciones de implementación
| Opción | Ventaja | Desventaja |
|--------|---------|------------|
| Solo menú contextual (actual) | Cero código nuevo | Se queda corto con más de ~8 opciones |
| Menú rápido + `Toplevel` con `ttk` | Liviano, nativo, sin dependencias | Algo más de código |
| Panel dentro del propio canvas | Estilo coherente | Hay que dibujar controles a mano: más código y accesibilidad pobre |
| Editar el JSON a mano | Cero UI | No es para usuarios normales |

**Recomendación**: menú rápido + `Toplevel` con `ttk`, generados desde una tabla declarativa.

## Esbozo del menú rápido
```
Vista            ▸  ● Anillos   ○ Barras
Tamaño           ▸  ● Completo  ○ Compacto
☑ Siempre encima
─────────────
Ajustes…
Actualizar ahora
Salir
```

## Esbozo de la ventana de ajustes
```
┌ Ajustes ───────────────────────┐
│ Apariencia                     │
│   Tema        [ Auto ▾ ]       │
│   Opacidad    ──●────  90 %    │
│ Datos                          │
│   Actualizar cada [ 15 s ▾ ]   │
│   Avisar en   70 %  y  90 %    │
│ Sistema                        │
│   ☑ Iniciar con Windows        │
│   [Restablecer]    [Cerrar]    │
└────────────────────────────────┘
```

## Orden sugerido
1. Mover `REFRESH_MS`, `TOKENS_EVERY`, umbrales y opacidad a `DEFAULT_CONFIG`.
2. Tabla declarativa de opciones y menú rápido generado desde ella.
3. Ventana de ajustes (`Toplevel` + `ttk`) con "Restablecer".
4. Engranaje al pasar el mouse.
5. Iniciar con Windows desde la ventana de ajustes.
