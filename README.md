# Mesa de Ayuda TI

Sistema de gestión de tickets de TI para las 6 empresas del grupo.
Flask + Bootstrap 5 + JWT + SQLAlchemy.

## Instalación

Necesitas Python 3.10 o superior.

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux o Mac

pip install -r requirements.txt
copy .env.example .env         # en Linux o Mac: cp .env.example .env
```

Abre `.env` y cambia `SECRET_KEY` y `JWT_SECRET_KEY` por textos largos y secretos.

## Primer arranque

```bash
flask --app run seed     # crea la base de datos con datos de prueba
python run.py            # abre http://127.0.0.1:5000
```

Cuentas de prueba (contraseña `demo1234` en todas):

| Correo | Rol |
|---|---|
| ana.diaz@empresa.pe | Administrador |
| luis.ramos@empresa.pe | Técnico |
| jorge.paredes@empresa.pe | Solicitante |

Para crear tu propio administrador sin datos de prueba:

```bash
flask --app run crear-admin
```

`flask --app run seed` **borra todo** y vuelve a cargar los datos de prueba.

## Estructura

```
run.py                     Punto de entrada
config.py                  Configuración (lee el archivo .env)
app/
  __init__.py              Crea la aplicación
  models.py                Tablas: users, tickets, ticket_fotos, ticket_historial,
                           notificaciones, tokens_revocados
  auth.py                  JWT, cierre de sesión y decorador @protegido("Rol")
  servicios.py             Reglas del negocio (las usan la web y la API)
  sla.py                   Cálculo del semáforo
  archivos.py              Validación MIME, carpeta /uploads y miniaturas
  reportes.py              Excel (openpyxl) y PDF (ReportLab)
  web.py                   Rutas de las páginas
  api.py                   API REST en /api
  comandos.py              flask seed y flask crear-admin
  templates/               HTML con Jinja y Bootstrap
    base.html              Estructura común
    partials/_header.html  Encabezado (igual en todas las páginas)
    partials/_footer.html  Pie de página (igual en todas las páginas)
  static/css/styles.css    Tema pastel sobre Bootstrap
  static/js/               app.js (común), nuevo-ticket.js, dashboard.js
uploads/                   Fotos de evidencia y miniaturas
postman/                   Colección para probar la API
```

## Cómo cumple cada módulo

1. **Autenticación y usuarios.** JWT con Flask-JWT-Extended. En la web viaja en una cookie HttpOnly con protección CSRF; en la API, en el header `Authorization: Bearer`. Contraseñas con bcrypt. Al cerrar sesión, el token se guarda en `tokens_revocados` y deja de servir. El decorador `@protegido("Administrador")` está en `app/auth.py`.
2. **Tickets con evidencias.** `request.files`, máximo 3 fotos, solo JPG o PNG. Se revisa el tipo MIME y además se abre la imagen con Pillow para confirmar que es real. Se guardan en `/uploads` con nombre aleatorio y miniatura de 240 px.
3. **Asignación, estados e historial.** Tabla `ticket_historial` con FK, fecha y texto obligatorio. Cambiar estado sin comentario devuelve error. La línea de tiempo muestra fechas relativas ("hace 3 h") con JavaScript.
4. **SLA y semáforo.** Alta 4 h, Media 24 h, Baja 72 h. Verde, amarillo (desde el 75 % del plazo) o rojo. El listado se ordena por urgencia y avisa cuando hay tickets vencidos o por vencer.
5. **Notificaciones.** Se crean al asignar, cambiar estado o comentar. La campana consulta `/api/notificaciones/contador` con `fetch` cada minuto. Se pueden marcar una por una o todas a la vez.
6. **Dashboard, reportes y API.** Conteos con `GROUP BY`, gráficos con Chart.js, filtros por fecha, área y responsable, exportación a Excel y PDF. La API está documentada en `postman/`.

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

## Usar PostgreSQL

```bash
pip install psycopg2-binary
```

En `.env`:

```
DATABASE_URL=postgresql://usuario:clave@localhost:5432/mesa_ayuda
```

Crea la base vacía en PostgreSQL y ejecuta `flask --app run seed`. Las tablas se crean solas.

## Ajustes rápidos

- Tiempos por prioridad y umbral del amarillo: `app/sla.py`.
- Empresas, áreas y categorías: `app/constantes.py`.
- Colores: variables al inicio de `app/static/css/styles.css`.
- Correo de soporte del pie: `CORREO_SOPORTE` en `.env`.
- Ocultar las cuentas de prueba del login: `MOSTRAR_CUENTAS_DEMO=0` en `.env`.

## Antes de publicarlo

- Cambia `SECRET_KEY` y `JWT_SECRET_KEY`.
- Pon `MOSTRAR_CUENTAS_DEMO=0`.
- Si usas HTTPS, pon `COOKIE_SECURE=1`.
- No uses `python run.py` en producción: usa un servidor como Gunicorn o Waitress.
