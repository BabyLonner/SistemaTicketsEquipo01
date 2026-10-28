# Módulo 3 (avance 2) — Etiquetas QR por equipo

Cada equipo informático de la empresa (laptop, PC, impresora, monitor…) tiene una **etiqueta QR**.
Al escanearla, el formulario de **Nuevo Ticket** se abre ya vinculado a ese equipo, con su
**ubicación** y su **historial de incidencias**.

Tecnologías: **qrcode.js** (dibuja el QR en pantalla), **html5-qrcode** (lee el QR con la cámara o
desde una foto) y **ReportLab** (PDF de etiquetas; ya lo usaba el módulo de reportes).
Las dos librerías JS están descargadas en `static/vendor/`, así que funcionan sin internet.

---

## 1. Archivos del módulo

| Archivo | Qué hace |
|---|---|
| `equipos.py` | **Nuevo.** Blueprint: registrar, editar y dar de baja equipos, regenerar QR, PDF de etiquetas, lectura del QR y enlace `/qr/<token>`. |
| `migrar_modulo3_qr.py` | **Nuevo.** Agrega la tabla y la columna a una base que ya tiene datos (no borra nada). |
| `database/mesa_ayuda_ti.sql` | Tabla `equipos`, columna `tickets.equipo_id` y 14 equipos de ejemplo (de las 6 empresas). |
| `templates/equipos.html` + `static/js/equipos.js` + `static/css/equipos.css` | **Nueva pantalla "Equipos"**: inventario con el QR de cada equipo, buscador, filtro y botón **Imprimir etiquetas (PDF)**. |
| `templates/nuevo_ticket.html` + `static/js/nuevo_ticket_qr.js` + `static/css/qr_equipo.css` | Bloque **"Escanear QR"** en Nuevo Ticket: cámara, foto del QR y ficha del equipo con su historial. |
| `templates/detalle_ticket.html` + `static/js/equipo_detalle.js` | Tarjeta **"Equipo afectado"** en el detalle del ticket. |
| `static/vendor/qrcode.min.js`, `static/vendor/html5-qrcode.min.js` | Librerías de QR (qrcode.js 1.0.0 y html5-qrcode 2.3.8). |
| `tickets.py` | 4 líneas: al registrar el ticket, si llega `equipo`, se vincula (y se valida). |
| `static/js/nuevo_ticket.js` | 2 líneas: envía el `equipo` escaneado y lo limpia después. |
| `run.py` | Registra `equipos_bp` y da permiso a la pantalla `equipos`. |
| `templates/base.html` | Opción **Equipos** en el menú (Administrador y Técnico). |

### Tabla `equipos`

| Campo | Para qué |
|---|---|
| `empresa_id`, `area_id` | De qué empresa y área es el equipo |
| `codigo` | Código patrimonial visible en la etiqueta (`AGF-PC-001`). Único por empresa |
| `nombre`, `tipo`, `marca`, `modelo`, `serie` | Datos del equipo |
| `ubicacion` | Dónde está físicamente ("Almacén, caja 2") |
| `qr_token` | Código **aleatorio** que va dentro del QR. Único |
| `activo` | 0 = dado de baja (se conserva su historial) |

`tickets.equipo_id` guarda el equipo escaneado. Con eso se arma el historial de incidencias.

### Rutas nuevas

| Ruta | Quién | Qué hace |
|---|---|---|
| `GET /equipos` | Admin, Técnico | Pantalla del inventario |
| `GET /api/equipos` | Admin, Técnico | Lista de equipos con su enlace QR |
| `POST /api/equipos` · `PUT /api/equipos/<id>` | Admin | Registrar / editar |
| `DELETE /api/equipos/<id>` | Admin | Dar de baja (no se borra) |
| `POST /api/equipos/<id>/regenerar-qr` | Admin | Token nuevo: la etiqueta vieja deja de servir |
| `GET /api/equipos/etiquetas.pdf?ids=1,2` | Admin, Técnico | PDF con etiquetas (2 × 5 por hoja A4) |
| `GET /api/equipos/qr/<token>` | Todos con sesión | Equipo + ubicación + historial (lo usa el escáner) |
| `GET /api/tickets/<id>/equipo` | Quien puede ver el ticket | Equipo del ticket (detalle) |
| `GET /qr/<token>` | Cualquiera | **Enlace que va en el QR.** Con sesión → Nuevo Ticket; sin sesión → login y luego vuelve |

---

## 2. Configuración

1. Copiar los archivos del módulo sobre el proyecto.
2. Base de datos:
   - **Base nueva o de pruebas:** `python inicializar_bd.py` (borra todo y carga los 14 equipos de ejemplo).
   - **Base con datos reales (PythonAnywhere):** `python migrar_modulo3_qr.py` (solo agrega; se puede repetir).
3. `.env`: la variable **`APP_URL_PUBLICA`** (la misma del módulo 4) decide qué dirección va dentro del QR.
   - Local: déjala vacía o pon `http://127.0.0.1:5000`.
   - PythonAnywhere: `https://usuario.pythonanywhere.com`.
   - ⚠ Si cambias la dirección, **vuelve a imprimir** las etiquetas.
4. No hay claves ni servicios externos: todo funciona dentro del sistema.

### Sobre la cámara
Los navegadores **solo permiten usar la cámara en HTTPS o en `localhost`**.
- En la laptop con `http://127.0.0.1:5000` la cámara funciona.
- En el celular hace falta HTTPS (PythonAnywhere ya lo tiene).
- Sin cámara: botón **"Subir foto del QR"** (lee el QR desde una imagen).
- El celular también puede escanear la etiqueta con **su cámara normal**: abre `/qr/<token>`, pide
  iniciar sesión si hace falta y llega al formulario con el equipo.

---

## 3. Cómo probarlo

1. Entrar como **administrador** (`christian.llontop@agrofutura.com.pe` / `Clave123`) → menú **Equipos**.
2. **Registrar equipo** → llenar código, nombre, tipo y ubicación → Guardar. Aparece con su QR.
3. Marcar uno o varios equipos → **Imprimir etiquetas (PDF)** (o **Etiqueta PDF** en una tarjeta).
4. Entrar como **solicitante** (`jorge.paredes@agrofutura.com.pe`) → **Nuevo** → **Escanear QR**,
   apuntar la cámara a la etiqueta (puede estar en el PDF abierto en el celular).
5. Aparece la ficha: código, ubicación, área, tipo, serie y **historial de incidencias**.
   El área y la categoría se completan solas. Escribir asunto y descripción → **Enviar Ticket**.
6. En el detalle del ticket aparece la tarjeta **"Equipo afectado"**, y en Equipos sube el contador
   de incidencias del equipo.

### Casos de error (para el video)

| Caso | Qué muestra el sistema |
|---|---|
| QR de otra página (no es del sistema) | "El QR apunta a otro sitio (…). Solo se aceptan etiquetas de este sistema." |
| QR de un equipo de **otra empresa** (p. ej. una etiqueta de EPSEL escaneada en Agrofutura) | "Este QR pertenece a un equipo de otra empresa." |
| QR **alterado** o etiqueta vieja después de **Regenerar QR** | "Este QR no corresponde a ningún equipo registrado…" |
| Equipo **dado de baja** | "El equipo … fue dado de baja y ya no recibe tickets." |
| Permiso de cámara negado | "Negaste el permiso de la cámara. Actívalo en el candado… o usa «Subir foto del QR»." |
| Foto sin QR o borrosa | "No se encontró un código QR en la imagen…" |
| Solicitante intenta abrir Equipos | Página 403: su rol no tiene permiso |

Aunque alguien se salte el navegador y mande un token falso con Postman, `tickets.py` vuelve a validar el
QR y **no registra el ticket** (se cancela toda la transacción).

---

## 4. Lo que se investigó

**Estructura de un código QR.** Es una matriz de cuadritos (módulos) negros y blancos. Tiene:
- 3 **patrones de posición** (los cuadros grandes de las esquinas), para que el lector encuentre y enderece el código.
- **Patrones de alineación y de sincronización**, que corrigen la perspectiva y marcan la cuadrícula.
- **Información de formato**: el nivel de corrección y la máscara usada.
- La **zona de datos** con los bytes y los bytes de corrección (Reed-Solomon).
- Una **zona de silencio** (margen blanco).

El tamaño se mide en **versiones** (1 = 21 × 21 módulos … 40 = 177 × 177). A más texto, más versión y
cuadritos más pequeños. Por eso el enlace es corto (`/qr/<token>`).

**Niveles de corrección de errores** (Reed-Solomon):

| Nivel | Recupera hasta | Uso |
|---|---|---|
| L | 7 % | Pantallas, máximo de datos |
| M | 15 % | Uso general |
| Q | 25 % | Ambientes industriales |
| **H** | **30 %** | **Etiquetas físicas que se rayan o ensucian (el que usamos)** |

Más corrección = más módulos para el mismo texto. Como el enlace es corto, nivel H no agranda mucho el QR.

**Qué conviene codificar.** Un **identificador o URL, nunca datos sensibles**. El QR es público: cualquiera
puede fotografiarlo. Por eso lleva solo `https://…/qr/kdJ8LIBx3sO0He6u`, sin el nombre del equipo, la
serie, la ubicación, la IP ni datos de personas. Los datos se muestran **después de iniciar sesión** y solo
a usuarios de la misma empresa. Ventaja extra: si el equipo se mueve o cambia de área, se edita en el
sistema y la etiqueta impresa sigue sirviendo.

**Cómo evitar que un QR alterado apunte a otro equipo.**
1. **Token aleatorio** de 96 bits (`secrets.token_urlsafe`) en lugar del id 1, 2, 3. Cambiar una letra
   no lleva "al siguiente equipo": no existe (hay 2⁹⁶ combinaciones).
2. **Validación por empresa** en el servidor: un QR de otra empresa se rechaza.
3. **Mismo dominio**: el escáner solo acepta enlaces de este sistema (evita QR falsos pegados encima que
   lleven a una página de phishing, el ataque conocido como *quishing*).
4. **Regenerar QR**: si una etiqueta se pierde o parece cambiada, el token se reemplaza y la etiqueta
   vieja deja de funcionar.
5. **Doble validación**: el navegador revisa, pero quien decide es el servidor (también al guardar el ticket).
6. Recomendación física: etiquetas con laminado o *anti-tamper* (se rompen si se despegan).

**Alternativas evaluadas.**
- **Generar QR:** qrcode.js (navegador, sin servidor) frente a la librería `qrcode` de Python (imágenes en
  el servidor). Se eligió qrcode.js para la pantalla y el widget QR de ReportLab para el PDF, porque
  ReportLab ya estaba instalado y no hubo que agregar dependencias.
- **Leer QR:** html5-qrcode (cámara + foto, funciona en celular y laptop) frente a la API nativa
  `BarcodeDetector` (no está en Firefox ni en Safari de escritorio) y frente a jsQR (solo decodifica y hay
  que programar la cámara). Se eligió html5-qrcode.

**Limitaciones.**
- La cámara requiere HTTPS o localhost.
- La lectura falla con poca luz, reflejos o etiquetas muy pequeñas (mínimo recomendado ≈ 2 × 2 cm; las
  nuestras miden 3,9 cm).
- Si cambia el dominio del sistema hay que reimprimir.
- El QR no prueba que la persona esté junto al equipo (alguien podría usar una foto de la etiqueta).
  Por eso el ticket igual pide sesión y queda registrado quién lo creó.

### Referencias
- DENSO WAVE — QR Code.com, "Error correction feature": <https://www.qrcode.com/en/about/error_correction.html>
- DENSO WAVE — QR Code.com, "Information capacity and versions": <https://www.qrcode.com/en/about/version.html>
- ISO/IEC 18004:2015 — QR Code bar code symbology specification.
- qrcode.js (davidshimjs): <https://github.com/davidshimjs/qrcodejs>
- html5-qrcode (mebjas): <https://github.com/mebjas/html5-qrcode>
- Mouse vs Python — "Reportlab: How to Create Barcodes in Your PDFs with Python" (QrCodeWidget): <https://blog.pythonlibrary.org/?p=3024>
- MDN — `getUserMedia()` y contextos seguros: <https://developer.mozilla.org/es/docs/Web/API/MediaDevices/getUserMedia>
- Python — módulo `secrets`: <https://docs.python.org/es/3/library/secrets.html>
- CNBC (2023) — "QR codes may be a gateway to identity theft, FTC warns" (quishing): <https://www.cnbc.com/2023/12/07/qr-codes-may-be-a-gateway-to-identity-theft-ftc-warns.html>
