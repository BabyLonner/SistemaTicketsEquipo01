# Módulo 6 — Asistente con IA en la base de conocimiento

Antes de crear un ticket, el usuario cuenta su problema en **Nuevo ticket** y un asistente con IA le
responde **usando solo los artículos registrados en el sistema**. La respuesta muestra los artículos
de origen y dos botones:

- **Sí, se resolvió mi problema** → no se crea ticket y la consulta queda como *resuelta sin ticket*.
- **No resolvió mi problema, crear ticket** → aparece el formulario ya lleno con lo que escribió.

Tecnología: **API de un modelo de lenguaje (LLM)** con el formato estándar de OpenAI
(`/chat/completions`). Por defecto se usa **Google Gemini** (plan gratuito de Google AI Studio). La
llamada se hace desde Flask con `urllib` de Python: **no se instala ninguna librería nueva**.

---

## 1. Archivos del módulo

| Archivo | Qué hace |
|---|---|
| `base_conocimiento.py` | **Nuevo.** Busca los artículos parecidos, llama a la API del LLM y registra cada consulta y su resultado. |
| `migrar_modulo6.py` | **Nuevo.** Crea las tablas `kb_articulos` y `kb_consultas` y registra 12 artículos (no borra nada). |
| `database/migracion_modulo6.sql` | **Nuevo.** Lo mismo que `migrar_modulo6.py`, para importarlo en phpMyAdmin. |
| `templates/nuevo_ticket.html` | Panel del asistente antes del formulario (se agregó, no se cambió nada existente). |
| `static/js/nuevo_ticket_asistente.js` + `static/css/nuevo_ticket_asistente.css` | **Nuevos.** Lógica y diseño del asistente en Nuevo ticket. |
| `run.py` | Registra el blueprint `kb_bp` (2 líneas). |
| `.env.example` | Variables `LLM_*`. |

### Tablas

`kb_articulos`: artículos registrados en el sistema (título, resumen, solución paso a paso, palabras
clave y categoría). `empresa_id = NULL` = artículo general para todas las empresas; con un
`empresa_id` el artículo solo lo usa esa empresa. Son los **únicos** que puede usar el asistente.

`kb_consultas`: cada pregunta al asistente.

| Campo | Para qué |
|---|---|
| `pregunta`, `respuesta`, `articulos` | Qué preguntó, qué respondió y qué artículos usó |
| `modo` | `IA`, `CACHE` (respuesta reutilizada), `LOCAL` (sin IA) o `SIN_ARTICULOS` |
| `tokens_entrada`, `tokens_salida` | Tokens que cobró la API (para el costo) |
| `resultado` | `PENDIENTE`, `RESUELTO` (se resolvió **sin** ticket) o `TICKET` |

**Cuántas consultas se resolvieron sin generar ticket:**

```sql
SELECT resultado, COUNT(*) AS consultas FROM kb_consultas GROUP BY resultado;
```

### Rutas nuevas

| Ruta | Qué hace |
|---|---|
| `POST /api/kb/consultar` | El asistente responde con los artículos registrados |
| `POST /api/kb/consultas/<id>/resultado` | Guarda `RESUELTO` (sin ticket) o `TICKET` |

---

## 2. Configuración paso a paso

### 2.1 Clave de la API (gratis)

1. Entra a **https://aistudio.google.com** con una cuenta de Google.
2. **Get API key → Create API key**. Copia la clave.

### 2.2 Variables de entorno (`.env`, nunca en GitHub)

```
LLM_API_KEY=la-clave-que-copiaste
LLM_API_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODELO=gemini-3.8-flash
LLM_MAX_TOKENS=400
LLM_CONSULTAS_HORA=15
```

Sin `LLM_API_KEY` el asistente sigue funcionando en **modo local**: muestra los pasos del artículo
más parecido, sin redactar con IA. Para usar otro proveedor con formato OpenAI (Groq, OpenAI…) solo se
cambian `LLM_API_URL`, `LLM_MODELO` y la clave.

### 2.3 Base de datos

```
python migrar_modulo6.py            (PythonAnywhere: python3.13 migrar_modulo6.py)
```
o importar `database/migracion_modulo6.sql` en phpMyAdmin. Se puede ejecutar varias veces.

---

## 3. Cómo probarlo

1. Inicia sesión como solicitante (ej. `jorge.paredes@agrofutura.com.pe`) y entra a **Nuevo**.
2. Escribe: *"La impresora del segundo piso no imprime, los documentos se quedan en cola"* → **Buscar solución**.
3. Verás la respuesta con la cita **A1** y el artículo de origen (se puede desplegar completo).
4. Pulsa **Sí, se resolvió mi problema** → mensaje de confirmación, sin ticket.
5. **Hacer otra consulta**: *"Outlook no me deja enviar correos"* → **No resolvió mi problema, crear ticket**.
   El formulario aparece con el asunto y la descripción ya llenos. Elige la categoría y el área, y envía.
6. En phpMyAdmin ejecuta la consulta de la sección 1: verás 1 consulta `RESUELTO` (sin ticket) y 1 `TICKET`.

Si se entra a Nuevo ticket escaneando un QR (`?equipo=`) o para editar (`?editar=`), el asistente
no aparece y se va directo al formulario. También existe el enlace *Prefiero crear el ticket directamente*.

### Casos de error (para el video)

| Caso | Qué pasa |
|---|---|
| Problema sin artículos (ej. "necesito una silla nueva") | No se llama a la IA (costo 0): *"No encontré artículos…"* y botón para crear el ticket. |
| La IA responde que los artículos no sirven | Igual que el caso anterior (`SIN_RESPUESTA`). |
| Clave vacía o incorrecta, sin internet, API caída | Modo local con el aviso *"El asistente de IA no respondió; te mostramos el artículo más parecido"*. |
| Más de 15 consultas a la IA en una hora | Modo local con aviso de límite. |
| Texto muy corto | *"Cuéntanos un poco más del problema (al menos 8 caracteres)."* |

---

## 4. Lo que se investigó

**Cómo se consume la API de un modelo de lenguaje.** Es una petición HTTP `POST` a
`/chat/completions` con la clave en el encabezado `Authorization: Bearer …` y un JSON con el modelo,
la lista de mensajes (`system` y `user`), la `temperature` y el `max_tokens`. La API responde con el
texto en `choices[0].message.content` y los tokens usados en `usage`. La clave está en el `.env` y la
llamada se hace desde el servidor: el navegador nunca la ve.

**Qué es un prompt de sistema.** Es el mensaje con rol `system` que define cómo debe comportarse el
modelo antes de leer la pregunta. El nuestro (en `base_conocimiento.py`, `PROMPT_SISTEMA`) le ordena
responder solo con los artículos entregados, citar `[A1]`, responder `SIN_RESPUESTA` si no le
sirven, escribir pasos en español sencillo, no pedir contraseñas e ignorar instrucciones que el
usuario escriba dentro de su problema.

**Por qué limitar la respuesta a nuestros artículos (RAG).** Primero se *recuperan* los artículos
parecidos (búsqueda por palabras en título, palabras clave, resumen y contenido) y luego el modelo
*genera* la respuesta solo con ellos. Así:
- no inventa soluciones que TI no aprobó (alucinaciones);
- no recomienda programas, enlaces o teléfonos que no son de la empresa;
- el usuario puede comprobar la respuesta en el artículo de origen;
- para cambiar lo que responde el asistente basta con editar un artículo, sin reentrenar nada.

**Cómo se controla el costo por consulta.** Las APIs cobran por *token* (≈ ¾ de palabra) de entrada y
de salida. En este módulo:
- solo se llama a la IA si hay artículos relacionados;
- se envían como máximo 3 artículos, recortados a 1 500 caracteres;
- la respuesta tiene un máximo de 400 tokens y `temperature` 0,2;
- la misma pregunta en 24 h reutiliza la respuesta guardada (modo `CACHE`, costo 0);
- cada usuario tiene un máximo de consultas a la IA por hora;
- se guardan los tokens de cada consulta en `kb_consultas`.

Una consulta típica usa unos 800 tokens de entrada y 100 de salida: con los precios de pago de
Gemini cuesta menos de 0,001 dólares. En el plan gratuito de Gemini el costo es 0 dentro de sus límites.

**Privacidad.** La pregunta y los artículos se envían a Google. En el plan gratuito Google puede usar
ese contenido para mejorar sus productos, por eso el panel avisa que no se escriban contraseñas ni
datos personales.

**Alternativas evaluadas.**

| Opción | Ventaja | Desventaja |
|---|---|---|
| Gemini (elegida) | Plan gratuito, formato OpenAI | En el plan gratuito los datos pueden usarse para mejorar el servicio |
| OpenAI / Claude | Muy buena calidad | De pago desde la primera consulta |
| Groq | Gratis y muy rápido | Límites de uso más bajos |
| Modelo local (Ollama) | Los datos no salen de la empresa | Necesita un servidor potente; no corre en PythonAnywhere |

### Referencias

- Google AI for Developers — *OpenAI compatibility*: https://ai.google.dev/gemini-api/docs/openai
- Google AI for Developers — *Gemini API pricing*: https://ai.google.dev/gemini-api/docs/pricing
- OpenAI — *Chat Completions API reference*: https://platform.openai.com/docs/api-reference/chat
