# Sistema de Tickets — Mesa de Ayuda TI (Equipo 01) · v2.1

Flask + MySQL (PyMySQL) · JWT · sin triggers ni vistas (funciona en PythonAnywhere).
Las interfaces (HTML/CSS) son las del equipo; esta versión corrige el backend y conecta todas las pantallas a la base de datos.

## Usuarios de prueba (contraseña de todos: `Clave123`)

| Rol | Correo |
|---|---|
| Superusuario | superadmin@mesadeayuda.com.pe |
| Admin Grupo M&M | victor.melgarejo@grupomm.com.pe |
| Admin Agrofutura | christian.llontop@agrofutura.com.pe |
| Admin EPSEL | sergio.goicochea@epsel.com.pe |
| Admin Clínica Provida | julio.salazar@clinicaprovida.com.pe |
| Admin Atlántica | elki.villacorta@atlantica.com.pe |
| Admin Ángel Divino Bus | hugo.tantajulca@angeldivinobus.com.pe |
| Técnico / Solicitante (ej. Ángel Divino) | renato.vega@... / rosa.villanueva@angeldivinobus.com.pe |

Cada empresa tiene además un técnico y un solicitante de ejemplo (ver `database/mesa_ayuda_ti.sql`).

**Cambien la contraseña antes de la sustentación:** clic en su nombre (arriba a la derecha) → **Mi Perfil** → Cambiar contraseña.

## Probar en tu PC (VS Code + XAMPP)

1. XAMPP → enciende MySQL. En phpMyAdmin crea la base `mesa_ayuda_ti` (utf8mb4_unicode_ci).
2. En la terminal de VS Code, dentro del proyecto:
   ```bash
   copy .env.example .env          # (Mac/Linux: cp .env.example .env)
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python inicializar_bd.py        # crea las tablas y los datos de ejemplo (responde s)
   python run.py
   ```
3. Abre http://127.0.0.1:5000

## Actualizar PythonAnywhere

1. **Respaldo** (consola Bash): `mysqldump -u jcachay -h jcachay.mysql.pythonanywhere-services.com --no-tablespaces -p 'jcachay$dawagr1' > ~/respaldo_antes_v21.sql`
2. Sube el código (git pull o subiendo los archivos) a la carpeta de la web app.
3. El `.env` va solo en el servidor (no en GitHub): `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`, `JWT_SECRET`.
4. `pip3.13 install --user -r requirements.txt` (usa la versión de Python de tu web app).
5. `python3.13 inicializar_bd.py` → **borra y vuelve a crear las tablas** (el esquema cambió).
6. Pestaña Web → **Reload**. Comprueba `https://grupo01.pythonanywhere.com/salud`.

## Módulo 8 — Reporte PDF verificable (QR + hash SHA-256)

Cada PDF que se descarga en **Reportes → Imprimir/PDF** lleva un código QR que apunta a
`URL_BASE/verificar/<codigo>`. Al generarlo, el servidor calcula la huella **SHA-256** del PDF terminado y la
guarda en la tabla `reportes_generados`. La página `/verificar/<codigo>` es pública (sin login): quien recibe el PDF
lo sube y el servidor recalcula la huella; si cambió un solo byte, el resultado es *Documento alterado*.

**Configuración**
- `.env` → `URL_BASE=http://127.0.0.1:5000` en tu PC, `URL_BASE=https://grupo01.pythonanywhere.com` en el servidor.
- Base de datos: si partes de cero, `python inicializar_bd.py` ya crea las tablas. Si ya tienes datos (PythonAnywhere),
  ejecuta solo `python3.13 migrar_modulo8.py`, que **no borra nada**.
- No requiere librerías nuevas: el QR lo dibuja ReportLab, el hash es `hashlib` y el correo es `smtplib` de Python.

**Cómo probarlo**
1. Inicia sesión como administrador o técnico → **Reportes** → botón PDF.
2. Escanea el QR con el celular (o abre el enlace impreso) → la página muestra los datos del reporte.
3. Sube el mismo PDF → **✅ Documento auténtico**.
4. Modifica el PDF (edítalo con cualquier editor de PDF y guárdalo) y súbelo → **❌ Documento alterado**.
5. Abre `/verificar/codigo-inventado-1234` → **Reporte no registrado**.

> El celular solo puede abrir el QR si `URL_BASE` es una dirección que alcance (PythonAnywhere o la IP de tu PC en la
> misma red Wi-Fi, ej. `http://192.168.1.20:5000` con `app.run(host="0.0.0.0")`).

### Envío semanal por correo (SMTP + tarea programada)

**1. Cuenta de Gmail.** Usen una cuenta solo para el proyecto. Activen la verificación en 2 pasos y creen una
contraseña de aplicación en https://myaccount.google.com/apppasswords. La contraseña normal no funciona.

**2. `.env`** (en cada PC y en el servidor; nunca en GitHub):
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=cuenta.del.proyecto@gmail.com
SMTP_PASSWORD=la-contraseña-de-aplicación
SMTP_REMITENTE=Mesa de Ayuda TI <cuenta.del.proyecto@gmail.com>
URL_BASE=https://grupo01.pythonanywhere.com
```

**3. Base de datos.** Si ya tienes datos: `python migrar_modulo8.py` (crea las tablas y agrega la columna `semanal`, sin
borrar nada). Los correos que ya existían quedan con envío semanal. Ejecuta también `python migrar_empresa_categorias.py`
(panel de SLA): sin esa tabla no se pueden crear tickets y el reporte se queda sin datos nuevos.

**4. Configuración → Reporte semanal por correo** (como administrador):
- **Lista de destinatarios:** agrega o elimina correos. La casilla *Envío semanal* indica quién recibe el envío automático.
- **Programación automática:** activa o desactiva el envío y elige el día. Se guarda por empresa y no hay que tocar el
  código. El reporte cubre los 7 días anteriores al día de envío (tickets creados en ese periodo).
- **Envío manual:** elige correos de la lista o escribe uno nuevo (se guarda sin envío semanal), elige las fechas
  *Desde* y *Hasta* y pulsa *Enviar ahora*. Pide confirmar a quién se envía.
- **Últimos envíos:** resultado de cada envío, manual o automático.

**5. Tarea programada en PythonAnywhere.** Pestaña **Tasks** → *Scheduled tasks*, una tarea diaria a las `13:00`
(hora UTC, son las 8:00 de Perú):
```
cd /home/<usuario>/<carpeta-del-proyecto> && python3.13 enviar_reportes.py
```
El script corre todos los días y revisa la programación de cada empresa: envía a las que les toca hoy y reintenta los
envíos que fallaron. Nunca repite un envío que ya salió bien. La **hora** no se elige en la pantalla: la cuenta gratuita
ejecuta la tarea una vez al día, a la hora definida en *Tasks*. El resultado se ve en el log de la tarea.

**Cómo probarlo**
| Prueba | Resultado esperado |
|---|---|
| Elegir tu correo, las fechas y pulsar *Enviar ahora* | Llega el PDF de esas fechas; su QR verifica como auténtico |
| Escribir un correo nuevo en *Otro correo* | Se envía y queda en la lista sin envío semanal |
| *Desde* posterior a *Hasta*, o *Hasta* futura | Error, no se envía nada |
| Cambiar el día y guardar | *Próximo envío* muestra la nueva fecha y el nuevo periodo |
| `SMTP_PASSWORD` incorrecta, reiniciar y enviar | ❌ en *Últimos envíos*: el servidor rechazó el usuario o la contraseña |
| `python enviar_reportes.py --forzar` | Envía hoy a los correos con envío semanal de las empresas activadas |
| `python enviar_reportes.py` dos veces el día programado | La segunda vez: "ya se envió el reporte" |

## Postman

Todas las rutas piden token:
1. `POST /api/login` con `{"correo": "...", "password": "Clave123"}` → copia `data.token`.
2. En cada petición: *Authorization → Bearer Token*. `POST /api/logout` invalida el token.

Las rutas `/api_insertar_*` y `/api_obtener_*` mantienen sus URL. Ver `CAMBIOS.md`.

## Estructura

```
run.py           app, login/logout JWT, notificaciones, dashboard, SLA, reportes y pantallas por rol
auth.py          JWT, sesión, roles, contraseñas (Módulo 1)
usuarios.py      API de usuarios (Módulo 1)
empresas.py      pantalla del superusuario (empresas + su administrador)
tickets.py       tickets, fotos, asignación, estados, historial, comentarios (Módulos 2-4)
reportes.py      exportar Excel/PDF y configuración de SLA (Módulos 4 y 6)
verificacion.py  verificación del PDF con QR + hash SHA-256 (Módulo 8)
correo.py        cliente SMTP: STARTTLS, login y PDF adjunto (Módulo 8)
envios.py        genera el reporte de un periodo, lo envía y guarda el historial (Módulo 8)
enviar_reportes.py   script de la tarea programada semanal (Módulo 8)
cuenta.py        Mi Perfil (cambiar contraseña) y Configuración de la empresa
api_postman.py   rutas de la colección de Postman (con JWT)
vistas.py        consultas que antes eran VISTAS de MySQL + SLA en Python
utils.py, config.py, db.py, inicializar_bd.py, probar_db.py
database/mesa_ayuda_ti.sql   base de datos sin triggers ni vistas
```
