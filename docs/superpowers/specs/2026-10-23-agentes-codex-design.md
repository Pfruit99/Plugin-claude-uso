# Límites de varios agentes (Claude + Codex) — diseño

Fecha: 2026-10-23 · Base: v0.2.0 (commit `44f9060`)

## Intención y el porqué

El widget responde a «¿puedo seguir trabajando?». Hoy solo mira Claude Code. Si Claude está agotado pero otro agente tiene cupo, la respuesta correcta es «sí, con Codex». Se añade Codex como **segundo agente con límites medibles**, y el widget pasa a decir *con cuál* puedes seguir.

Solo se incluyen agentes cuyos límites se pueden **medir de verdad**. Gemini, Qwen y OpenCode no exponen un límite local (solo contadores de peticiones o nada) y Cursor no guarda nada en local: quedan fuera, y **no se inventan ni simulan datos**.

## Objetivos

1. Leer las ventanas de límite de Codex (porcentaje, hora de reinicio y duración) con la sesión de ChatGPT del propio Codex. Las ventanas dependen del plan: no se asumen 5 h y semanal.
2. Estructura de **proveedores**: un `LimitsProvider` por agente que devuelve el mismo `Limits` que ya existe. Claude pasa a ser el primero sin cambiar su comportamiento.
3. Estado combinado: el widget muestra el estado del **mejor agente disponible** y nombra cuál usar.
4. Ajustes: activar Codex, ver si hay sesión y botón **Iniciar sesión** que lanza `codex login`.
5. Sin Codex activado, todo funciona exactamente como en 0.2.0.

## No-objetivos

- Gemini, Qwen, OpenCode, Cursor y Copilot.
- Contar tokens de Codex (solo límites).
- Cuentas de Codex con clave de API, o varias cuentas a la vez.
- Leer, guardar o enviar credenciales: el widget nunca toca `auth.json` ni el token.

## Anti-objetivos (fracaso aunque funcione)

- Que el widget se cuelgue o deje procesos `codex` huérfanos por una consulta lenta o fallida.
- Que gaste CPU en reposo o consulte más de lo necesario.
- **Mostrar ceros o valores inventados** cuando no hay datos: sin sesión o sin datos se muestra como tal.
- Que quien no usa Codex vea algún cambio o aviso.

## Restricciones

- Windows 10/11, Python 3.10+, PySide6. Sin dependencias nuevas.
- El protocolo de `codex app-server` está marcado **experimental**: cualquier fallo se trata con elegancia y se registra en el log, sin romper el widget.
- Confirmado en el esquema que genera el propio `codex.exe` (v0.162.0-alpha): método `account/rateLimits/read`; respuesta con `rateLimits.primary` / `secondary` = `{usedPercent: int, resetsAt: int|null (epoch), windowDurationMins: int|null}`, además de `planType`, `credits` y `rateLimitsByLimitId`.
- Estado en este PC: Codex viene en la extensión de VS Code (`...\.vscode\extensions\openai.chatgpt-*\bin\windows-x86_64\codex.exe`) y no está en el PATH. **La sesión ya está iniciada** (ChatGPT).

## Hallazgo de la prueba real (2026-10-23)

Se consultó `account/rateLimits/read` en esta cuenta, sin tocar el token (respuesta guardada sin `accountId`):

- Protocolo: **JSON por líneas** (un mensaje por línea) sobre stdio. `initialize` con `clientInfo{name,version}` responde en ~0,7 s; tras la notificación `initialized`, la lectura tarda ~1 s. Entre medias llegan notificaciones (`remoteControl/status/changed`, `account/updated`) que se ignoran.
- Plan **free**: `primary = {usedPercent: 0, windowDurationMins: 43200 (30 días), resetsAt: epoch}` y **`secondary = null`**. No hay ventana de 5 h ni semanal.
- Consecuencia: las ventanas se identifican por su **duración**, no por su nombre.

## Approaches considerados

| # | Enfoque | Compensación |
|---|---------|--------------|
| A | Preguntar a `codex app-server` (JSON-RPC por stdio) con `account/rateLimits/read` | Datos frescos y exactos con la sesión del propio Codex; protocolo experimental; hay que lanzar un proceso |
| B | Leer los archivos de sesión de Codex | Sin proceso ni login, pero solo se actualiza al usar Codex y hoy no hay datos |
| C | Leer el token de `auth.json` y llamar al servicio | Descartado: maneja un secreto y usa un servicio no documentado |

**Elegido: A** (con la confirmación del usuario de que tiene cuenta de ChatGPT).

## Diseño

### Estructura

```
claude_usage/
  providers/
    __init__.py      PROVIDERS = {"claude": ClaudeProvider(), "codex": CodexProvider()}
    base.py          Reading, ReadingState, protocolo LimitsProvider
    claude.py        envuelve limits.read_limits (sin cambios de comportamiento)
    codex.py         localizar el binario, cliente JSON-RPC, parse_rate_limits()
  agents.py          combina los estados de los agentes activos (función pura)
```

- `Reading` = `(limits: Limits, state, message)`; `state` ∈ `ok`, `sin_sesion`, `no_instalado`, `error`, `pendiente`.
- Un proveedor expone `label`, `poll_seconds` y `read() -> Reading`. Nunca lanza excepciones: las convierte en un `Reading` con estado.
- `Window` gana dos campos opcionales: `span` (segundos) y `label`. Si faltan se usan los de Claude (5 h → «5 h», 7 d → «Semana»).
- Codex ocupa las dos ranuras existentes **por duración**: una ventana de hasta 1 día va a la ranura corta (`five`) y una más larga a la larga (`week`). Etiqueta según los minutos: 300 → «5 h», 10080 → «Semana», 43200 → «Mes», otra → «N h» o «N d». Con el plan free de esta cuenta: ranura corta vacía y larga = «Mes».
- Los estilos y textos dejan de usar los nombres fijos «5 h» / «Semana» y leen `window.label` y `window.span`.

### Cliente de Codex

1. Localizar el binario: `codex` en el PATH, `%APPDATA%\npm`, y la extensión más reciente `openai.chatgpt-*` de VS Code o Cursor. El resultado se guarda en caché; si no aparece, estado `no_instalado`.
2. Lanzar `codex app-server` sin ventana, enviar `initialize` + notificación `initialized`, pedir `account/rateLimits/read`, leer la respuesta y **terminar el proceso**. Tiempo máximo total: 15 s; al agotarse se mata el proceso.
3. Si Codex responde que no hay sesión → `sin_sesion`. Cualquier otro fallo → `error` con mensaje corto y entrada en el log.
4. `parse_rate_limits(respuesta) -> Limits` es una función pura: toma `primary` y `secondary` (los que no sean `null`), los ordena por duración y los reparte en las ranuras corta y larga. Con una sola ventana, la otra ranura queda vacía.

### Consulta y datos

- Cada proveedor se lee **fuera del hilo de la interfaz** (como el conteo de tokens) y avisa por señal.
- Codex se consulta al arrancar (si está activado), después cada 5 minutos **solo con el widget visible**, y al pulsar «Actualizar ahora». Nunca dos consultas a la vez.
- Datos de cualquier agente con más de 15 minutos se señalan como desactualizados, como los de Claude.

### Estado combinado (`agents.py`)

- Se calcula el `Status` de cada agente activo con los mismos umbrales (Ojo/Frena) y el ritmo.
- **Agente elegido** = el de mejor nivel (*Libre* < *Ojo* < *Frena*). **Con empate de nivel manda Claude** (el primero de la lista): solo se pasa a otro agente si está en un nivel estrictamente mejor. *(Cambiado tras la prueba real: con «menor uso» como desempate, el 0 % mensual de Codex ganaba siempre y ocultaba a Claude.)* El estado global es el del elegido.
- Por tanto *Frena* global solo ocurre cuando **todos los agentes activos con datos** están en *Frena*. Si Claude frena pero Codex no, el estado es el de Codex y la frase lo dice: «Claude frena · sigue con Codex».
- Agentes sin sesión o sin datos no cuentan para el estado global. Los datos con más de 15 minutos **sí cuentan** (se señalan como desactualizados y no generan avisos). *(Cambiado tras la prueba real: Claude solo actualiza sus datos mientras se usa Claude Code, y tratarlos como inválidos hacía saltar el widget a Codex cada vez que dejabas Claude quieto.)*
- Con solo Claude activo, el resultado es idéntico al actual.

### Interfaz

- **Semáforo**: la palabra y la barra son las del agente elegido; una línea de chips muestra el estado de cada agente activo («● Claude Frena · ● Codex Libre»).
- **Margen**: titular y barra del agente elegido; el título nombra el agente («Codex · 5 h»).
- **Píldora**: «Libre · Codex 2 h 10 min»; al pasar el ratón, filas por agente con 5 h y semanal.
- **Clásico**: sigue siendo solo Claude (decisión mía).
- Bandeja: el tooltip lista cada agente. Los avisos de Windows usan el estado global y nombran el agente.
- Ajustes, sección **Agentes**: casilla «Codex», etiqueta con el estado («Conectado», «Sin sesión», «No instalado»), botón **Iniciar sesión** (lanza `codex login`; abre el navegador) y reintento automático al volver.

### Configuración

Claves nuevas con valor por defecto: `codex_enabled` (false) y `codex_path` (vacío = autodetectar). Compatible hacia atrás.

### Pruebas y datos reales

- El analizador se prueba con la **respuesta real ya capturada** (plan free, una ventana de 30 días, sin `accountId`). Si la cuenta cambia de plan se añade su captura real. No hay respuestas inventadas: el caso de «dos ventanas» se prueba con esa misma captura alterada solo en su forma, y la prueba lo indica.
- El cliente se prueba con un servidor de pruebas que habla el protocolo (doble del proceso, no de los datos): tiempo agotado, proceso que muere, sesión ausente.
- `agents.py` y el estado combinado son funciones puras con pruebas propias.

### Orden de trabajo

1. Refactor a proveedores con Claude, sin cambios visibles; pruebas verdes.
2. Cliente de Codex y captura de una respuesta real (requiere que el usuario inicie sesión).
3. Analizador con esa captura, estado combinado y sus pruebas.
4. Interfaz de los tres estilos, bandeja y avisos.
5. Ajustes (casilla, estado, botón de sesión) y documentación.

## Decisiones mías (sin confirmar por el usuario)

- *Frena* global solo cuando todos los agentes activos están en *Frena*.
- Clásico se queda con Claude solamente.
- Consulta cada 5 min y solo con el widget visible.
- Codex desactivado por defecto; sin Codex nada cambia.
- Versión nueva: 0.3.0.

## Se deja al constructor

- Orden de búsqueda del binario y mensajes de error exactos.
- Diseño de los chips y las filas por agente.
- Cuándo y cómo reintentar tras un fallo.
