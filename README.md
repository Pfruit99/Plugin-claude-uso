# Widget de uso de Claude

Widget de escritorio para Windows que muestra de un vistazo cuánto te queda del límite de 5 horas y del límite semanal de Claude Code, junto con los tokens de hoy y de la semana y el porcentaje de contexto.

Usa solo la biblioteca estándar de Python (tkinter): sin dependencias que instalar.

## Cómo funciona

1. `statusline.ps1` lo ejecuta Claude Code como línea de estado y guarda los límites en `~\.claude\usage_limits.json`.
2. `widget.py` lee ese archivo, cuenta los tokens de los logs en `~\.claude\projects\**\*.jsonl` y dibuja el widget.

## Requisitos

- Windows 10/11
- Python 3.10 o superior (con tkinter)
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

```powershell
pythonw widget.pyw
```

O haz doble clic en `widget.pyw`. Para ver errores en consola usa `python widget.py`.

### 3. Iniciar con Windows (opcional)

Desde **Ajustes → Iniciar con Windows**, o con:

```powershell
powershell -ExecutionPolicy Bypass -File instalar_inicio.ps1
```

## Controles

| Acción | Resultado |
|--------|-----------|
| Arrastrar | Mueve el widget (la posición se guarda) |
| Clic derecho, o clic en ⚙ | Abre el panel de opciones |
| Doble clic | Alterna entre tamaño completo y compacto |
| Clic en ↻ (modo completo) | Actualiza al instante |
| `R` / `Esc` en el panel | Actualizar / cerrar |

### Panel de opciones

Selectores con icono de un solo clic para **Vista** (anillos o barras), **Tamaño** (compacto o completo) y **Tema** (automático, claro u oscuro), más las acciones **Ajustes…**, **Actualizar ahora** y **Salir**.

### Ajustes

- **Apariencia:** tema y opacidad (30–100 %).
- **Datos:** intervalo de actualización (5, 15, 30 o 60 s) y umbrales de aviso amarillo y rojo (por defecto 70 % y 90 %).
- **Sistema:** iniciar con Windows y restablecer valores.

Todo se aplica y se guarda al instante en `~\.claude-usage-widget.json`. Los valores fuera de rango vuelven al valor por defecto.

## Cambios

### Correcciones
- "Actualizar ahora" ya no crea una cadena nueva de refrescos en cada clic.
- La marca de tiempo de `statusline.ps1` usa UTC real (`ToUnixTimeSeconds`); antes `Get-Date -UFormat %s` podía desfasar la hora en PowerShell 5.1.

### Rendimiento
- El widget solo redibuja cuando cambia algo (límites, tokens, configuración o el minuto).
- El tema de Windows se consulta como mucho cada 30 s.
- El conteo de tokens lee los logs de forma incremental (desde el último offset), guarda fechas ya convertidas y poda archivos viejos: de 0,44 s la primera lectura a 0,005 s las siguientes.
- `statusline.ps1` solo reescribe el JSON si cambió algún valor o tiene más de 60 s.
- Intervalo de actualización por defecto: 15 s (antes 5 s).

### Interfaz
- Texto nítido en pantallas con escala superior al 100 % (DPI awareness); el dibujo y los clics se reescalan.
- Transición suave de anillos, barras y porcentajes (~60 fps solo mientras un valor cambia).
- Engranaje ⚙ al pasar el mouse sobre el widget.
- Nuevo panel de opciones gráfico con selectores con icono, con la paleta y opacidad del widget (el menú nativo queda como respaldo).
- Nueva ventana de **Ajustes** con validación de rangos y botón de restablecer.
- La posición se corrige si el monitor cambió y el widget quedaría fuera de pantalla.

### Robustez
- Arranque sin consola con `widget.pyw` + `pythonw`.
- Instancia única (no se abren dos widgets).
- Los errores se guardan en `~\.claude-usage-widget.log` (se recorta pasados 100 KB).

## Estructura

| Archivo | Descripción |
|---------|-------------|
| `widget.py` | Widget, panel de opciones, ajustes y conteo de tokens |
| `widget.pyw` | Lanzador sin consola |
| `statusline.ps1` | Línea de estado de Claude Code que escribe los límites |
| `instalar_inicio.ps1` | Crea el acceso directo de inicio con Windows |
| `docs/brainstorm/` | Notas de diseño y análisis de mejoras |
