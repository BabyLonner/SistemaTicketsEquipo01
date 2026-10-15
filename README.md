# Mesa de Ayuda TI

Sistema de tickets de TI para las 6 empresas del grupo.
Flask + MySQL (PyMySQL) + Bootstrap 5, con la misma organización que trabajamos en clase.

## Estructura

```
mesa-ayuda-ti/
├── app.py                         Aplicación principal: app = Flask(__name__) y las rutas @app.route
├── bd.py                          obtenerconexion() con PyMySQL
├── api.py                         Rutas de la API REST (/api/...)
├── seguridad.py                   JWT y decorador @requiere_sesion("Rol")
├── controlador_usuarios.py        Consultas SQL de usuarios
├── controlador_tickets.py         Consultas SQL de tickets, fotos e historial
├── controlador_notificaciones.py  Consultas SQL de notificaciones
├── controlador_reportes.py        Dashboard (GROUP BY), Excel y PDF
├── utilidades.py                  Listas fijas, cálculo del SLA y manejo de fotos
├── cargar_datos.py                Carga datos de prueba
├── crear_admin.py                 Crea un administrador
├── sql/
│   └── mesa_ayuda_ti.sql          Script de la base de datos
├── templates/
│   ├── base.html                  Estructura común (incluye header y footer)
│   ├── _header.html               Encabezado común
│   ├── _footer.html               Pie de página común
│   ├── _toasts.html               Mensajes emergentes
│   ├── _macros.html               Etiquetas de estado, prioridad y SLA
│   ├── login.html
│   ├── dashboard.html
│   ├── tickets.html
│   ├── nuevo_ticket.html
│   ├── detalle_ticket.html
│   ├── notificaciones.html
│   ├── usuarios.html
│   └── error.html
├── static/
│   ├── css/style.css
│   ├── js/app.js                  Login con fetch, campana, fechas relativas
│   ├── js/nuevo_ticket.js         Vista previa de fotos
│   ├── js/dashboard.js            Gráficos con Chart.js
│   └── img/
├── uploads/                       Fotos de evidencia (no son públicas como /static)
└── postman/                       Colección para probar la API
```

## Cómo ejecutarlo

1. Enciende **Apache y MySQL** en XAMPP.
2. En phpMyAdmin, pestaña **SQL**, pega y ejecuta el contenido de `sql/mesa_ayuda_ti.sql`.
   Crea la base `mesa_ayuda_ti` con sus tablas.
3. Instala las librerías (dentro de tu `.venv`, como en clase):

   ```bash
   pip install -r requirements.txt
   ```

4. Carga los datos de prueba:

   ```bash
   python cargar_datos.py
   ```

5. Ejecuta la aplicación:

   ```bash
   flask --app app run --debug
   ```

   o también `python app.py`. Luego abre http://127.0.0.1:5000

Si tu MySQL tiene contraseña o usa otro puerto, cámbialo en `bd.py`.

### Cuentas de prueba

Todas usan la contraseña `demo1234`.

| Correo | Rol |
|---|---|
| ana.diaz@empresa.pe | Administrador |
| luis.ramos@empresa.pe | Técnico |
| jorge.paredes@empresa.pe | Solicitante |

`python cargar_datos.py` **borra todo** y vuelve a cargar los datos de prueba.
Para empezar sin ellos, usa `python crear_admin.py`.

## Cómo cumple cada módulo

1. **Autenticación y usuarios.** El login se envía con `fetch` a `/procesar_login`, igual que en clase. Las contraseñas se guardan cifradas con bcrypt. Se usa JWT (Flask-JWT-Extended): en la web va en una cookie protegida y en la API, en el header `Authorization`. Al cerrar sesión, el token se guarda en `tokens_revocados` y deja de servir. El decorador `@requiere_sesion("Administrador")` está en `seguridad.py`.
2. **Tickets con evidencias.** Las fotos llegan por `request.files`, máximo 3, solo JPG o PNG. Se revisa el tipo MIME y además se abre la imagen para confirmar que es real. Se guardan en `uploads/` con una miniatura.
3. **Asignación, estados e historial.** Tabla `ticket_historial` con FK, fecha y texto obligatorio. Cambiar de estado sin comentario muestra un error. La línea de tiempo muestra fechas relativas ("hace 3 h") con JavaScript.
4. **SLA y semáforo.** Alta 4 h, Media 24 h, Baja 72 h. El color pasa a amarillo al 75 % del plazo y a rojo al vencer. El listado se ordena por urgencia y avisa de los tickets vencidos o por vencer.
5. **Notificaciones.** Se crean al asignar, cambiar de estado o comentar. La campana consulta `/api/notificaciones/contador` con `fetch` cada minuto. Se pueden marcar una por una o todas a la vez.
6. **Dashboard, reportes y API.** Conteos con `GROUP BY`, gráficos con Chart.js, filtros por fecha, área y responsable, y exportación con openpyxl y ReportLab. La API está documentada en `postman/`.

## Permisos

| Acción | Administrador | Técnico | Solicitante |
|---|---|---|---|
| Ver tickets | Todos | Todos | Solo los suyos |
| Crear tickets y comentar | Sí | Sí | Sí |
| Asignar técnico | Sí | No | No |
| Cambiar estado | Sí | Solo los asignados a él | No |
| Gestionar usuarios | Sí | No | No |

## Probar la API con Postman

1. Importa `postman/Mesa_Ayuda_TI.postman_collection.json`.
2. Con la app corriendo, ejecuta **Autenticación > Iniciar sesión**. El token se guarda solo.
3. Prueba las demás peticiones. Cambia `ticket_id` y `usuario_id` en las variables de la colección.

## Ajustes rápidos

- Conexión a MySQL: `bd.py`.
- Claves secretas, correo de soporte y botones de prueba del login: inicio de `app.py`.
- Tiempos del SLA, empresas, áreas y categorías: `utilidades.py`.
- Colores: variables al inicio de `static/css/style.css`.
