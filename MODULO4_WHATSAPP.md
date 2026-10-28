# Módulo 4 — Aviso al técnico por WhatsApp (Vonage)

Cuando un ticket se **asigna o reasigna** a un técnico, el sistema le envía un WhatsApp con el
código, la prioridad, el asunto y el enlace al ticket. Cada mensaje queda registrado en la base de
datos con su estado, y el técnico configura su número en **Mi Perfil**.

```
*MesaTI – Agrofutura*
Hola Sofía, te asignaron el ticket *AGF-0003* (prioridad Baja).
Acceso al sistema de planillas
Revísalo aquí: https://.../detalle_ticket?id=14
```

Tecnología: **Vonage Messages API** (antes Nexmo), con su **Sandbox de WhatsApp** gratuito.
Se cambió Twilio por Vonage con autorización del docente.

---

## 1. Archivos del módulo

| Archivo | Qué hace |
|---|---|
| `avisos_whatsapp.py` | **Nuevo.** Conexión con Vonage: arma el mensaje, lo envía, lo registra y recibe el webhook de estado. |
| `migrar_modulo4.py` | **Nuevo.** Agrega la columna y la tabla a una base que ya tiene datos (no borra nada). |
| `database/mesa_ayuda_ti.sql` | Columna `users.telefono` y tabla `mensajes_externos`. |
| `tickets.py` | Al asignar/reasignar, después de guardar, llama a `avisar_asignacion()`. `/api/tecnicos` indica quién tiene WhatsApp. |
| `api_postman.py` | La asignación por la API de Postman también envía el aviso. |
| `run.py` | Registra el blueprint `avisos_bp`. |
| `templates/perfil.html` + `static/js/perfil_whatsapp.js` + `static/css/perfil_whatsapp.css` | Sección **WhatsApp para avisos** en Mi Perfil (solo técnicos): guardar número y enviar prueba. |
| `templates/asignacion.html` + `static/js/asignacion.js` + `static/css/asignacion.css` | Panel **Avisos por WhatsApp** (registro y botón Reintentar) y etiqueta "Recibirá aviso por WhatsApp" al asignar. |
| `.env.example` | Variables de Vonage. |

### Tabla `mensajes_externos`

| Campo | Para qué |
|---|---|
| `ticket_id`, `tecnico_id`, `enviado_por` | Qué ticket, a quién y quién asignó |
| `canal` | `WHATSAPP` o `SMS` |
| `motivo` | `ASIGNACION`, `REASIGNACION` o `PRUEBA` |
| `telefono`, `mensaje` | Número y texto enviados |
| `proveedor_id` | `message_uuid` que devuelve Vonage (sirve para el webhook) |
| `estado` | `PENDIENTE` → `ENVIADO` → `ENTREGADO` → `LEIDO`, o `FALLIDO` |
| `error_detalle`, `intentos` | Motivo del fallo y cuántas veces se intentó |

### Rutas nuevas

| Ruta | Quién | Qué hace |
|---|---|---|
| `GET / PUT /api/mi-whatsapp` | Usuario con sesión | Ver / guardar su número |
| `POST /api/mi-whatsapp/prueba` | Usuario con sesión | Enviarse un mensaje de prueba |
| `GET /api/avisos` | Administrador | Últimos mensajes y su estado |
| `POST /api/avisos/<id>/reintentar` | Administrador | Reenviar un aviso fallido |
| `POST /webhooks/vonage/estado?token=...` | Vonage | Actualiza el estado (entregado, leído, rechazado) |
| `POST /webhooks/vonage/entrante?token=...` | Vonage | Mensajes que el técnico escribe al Sandbox (solo responde 200) |

---

## 2. Configuración paso a paso

### 2.1 Cuenta de Vonage
1. Crear cuenta en <https://dashboard.nexmo.com/sign-up> (no pide tarjeta; da USD 2 de crédito).
2. En el panel copiar **API key** y **API secret** (el secreto se muestra una sola vez).
3. Ir a **Messaging → Messages Sandbox → WhatsApp → Add to sandbox**.

### 2.2 Unir el WhatsApp del técnico al Sandbox
Desde el celular del técnico, enviar por WhatsApp al número **+1 415 738 6102** la frase que muestra
el panel (por ejemplo `Join ebony nerd`). Vonage responde *"Your number is now set up…"*.
Cada técnico que vaya a recibir avisos debe hacer este paso una vez.

### 2.3 Variables de entorno (`.env`, nunca en GitHub)
```
VONAGE_API_KEY=xxxxxxxx
VONAGE_API_SECRET=xxxxxxxxxxxxxxxx
VONAGE_CANAL=whatsapp
VONAGE_SANDBOX=1
VONAGE_WHATSAPP_FROM=14157386102
VONAGE_WEBHOOK_TOKEN=una-frase-larga-que-nadie-sepa
APP_URL_PUBLICA=https://tu-direccion-publica
```
Si faltan las claves, el sistema **no se cae**: la asignación se guarda igual y el aviso queda como
`FALLIDO` con el motivo "Vonage no está configurado".

### 2.4 Base de datos
- Base nueva: `python inicializar_bd.py` (borra y crea todo).
- Base con datos (PythonAnywhere): `python migrar_modulo4.py` (solo agrega, se puede repetir).

### 2.5 Webhook de estado (opcional, para ver "Entregado" y "Leído")
Vonage necesita una dirección **pública**:
- Local: ejecutar `ngrok http 5000` y usar la dirección `https://xxxx.ngrok-free.dev`.
- PythonAnywhere: `https://usuario.pythonanywhere.com`.

En **Messages Sandbox → Webhooks**:
- **Status:** `https://TU-DIRECCION/webhooks/vonage/estado?token=EL_MISMO_VONAGE_WEBHOOK_TOKEN`
- **Inbound:** `https://TU-DIRECCION/webhooks/vonage/entrante?token=EL_MISMO_VONAGE_WEBHOOK_TOKEN`

Pulsar **Save webhooks**. Sin webhook los mensajes igual se envían; solo se quedan en `ENVIADO`.

---

## 3. Cómo probarlo
1. Entrar como **técnico** → **Mi Perfil** → escribir el celular → **Guardar número** → **Enviar prueba**.
2. Entrar como **administrador** → **Asignación** → **Asignar** un ticket a ese técnico.
   Debe salir: *"✆ Aviso por WhatsApp enviado a …"* y el mensaje llega al celular.
3. En el panel **Avisos por WhatsApp** aparece el registro con su estado.

### Casos de error (para el video)
| Caso | Qué muestra el sistema |
|---|---|
| Técnico sin número en su perfil | Etiqueta "Sin WhatsApp en su perfil" y aviso `FALLIDO`: "El técnico no tiene número…" |
| Número no unido al Sandbox | `FALLIDO` con el mensaje de Vonage; luego **Reintentar** |
| Claves incorrectas | `FALLIDO`: "Credenciales de Vonage incorrectas" |
| Número mal escrito | Mi Perfil no deja guardar: "Un celular de Perú tiene 9 dígitos y empieza con 9" |

---

## 4. Lo que se investigó

**Cómo funciona la API.** El servidor hace un `POST` HTTPS a
`https://messages-sandbox.nexmo.com/v1/messages` con autenticación *Basic* (API key + secret) y un
JSON con `from`, `to`, `channel`, `message_type` y `text`. Vonage responde `202 Accepted` con un
`message_uuid`: eso significa "recibido", **no** "entregado".

**Webhook de estado.** Es Vonage quien llama a nuestro servidor (al revés de una API normal) para
avisar el estado final: `submitted`, `delivered`, `read`, `rejected` o `undeliverable`. Con el
`message_uuid` se actualiza la fila. Se protege con un token en la URL, se responde siempre 200
(si no, Vonage reintenta durante 24 horas) y nunca se retrocede de estado porque los avisos
pueden llegar desordenados.

**Restricciones del Sandbox.**
- Solo envía a números que se unieron con la frase *Join …*.
- Ventana de 24 horas de WhatsApp: el técnico debe haber escrito al número del Sandbox en las
  últimas 24 h; si no, el mensaje no llega. Antes de la demo, enviar un "hola".
- Unos 100 mensajes al mes y 1 mensaje por segundo.
- No permite plantillas (*templates*) y el remitente es el número de Vonage, no el de la empresa.
- Es solo para pruebas, no para producción.

**Costo en un entorno real (aproximado).**
- Vonage cobra una tarifa de plataforma desde ~USD 0,00016 por mensaje, más la tarifa de Meta.
- Meta cobra por mensaje desde julio de 2025. Los mensajes dentro de la ventana de 24 h son gratis.
  Un aviso de asignación fuera de esa ventana debe ir como plantilla **utility**, con el precio de
  Meta para Perú.
- Como referencia, un SMS a Perú cuesta alrededor de USD 0,25 por mensaje en Twilio.

**PythonAnywhere.** Las cuentas gratuitas solo permiten salir a sitios de una lista blanca. Si
`messages-sandbox.nexmo.com` no está permitido, el aviso queda `FALLIDO` con "No se pudo conectar
con Vonage". En ese caso se prueba en local con ngrok o se pide el dominio a PythonAnywhere.

### Referencias
- Vonage — Messages API Sandbox: <https://developer.vonage.com/en/messages/concepts/messages-api-sandbox>
- Vonage — Messages API (Basic o JWT): <https://developer.vonage.com/en/messages/technical-details>
- Vonage — Números de prueba en la cuenta trial: <https://api.support.vonage.com/hc/en-us/articles/204014853>
- Vonage — Precios de WhatsApp: <https://www.vonage.com/communications-apis/messages/features/whatsapp/pricing/>
- Meta — Precios de WhatsApp Business: <https://developers.facebook.com/docs/whatsapp/pricing>
- Twilio — Precio de SMS a Perú: <https://www.twilio.com/sms/pricing/pe>
- PythonAnywhere — Lista blanca: <https://www.pythonanywhere.com/whitelist/>
