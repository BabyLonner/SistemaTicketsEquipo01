# Mesa de Ayuda TI — Sistema de tickets para las 6 empresas del grupo

Flask + MySQL (PyMySQL) · JWT · sin triggers (compatible con PythonAnywhere).

## Usuarios de prueba (contraseña de todos: `Clave123`)

| Rol | Correo |
|---|---|
| Superusuario | superadmin@mesadeayuda.com.pe |
| Admin Grupo M&M | victor.melgarejo@grupomm.com.pe |
| Admin Agrofutura | christian.llontop@agrofutura.com.pe |
| Admin EPSEL | sergio.goicochea@epsel.com.pe |
| Admin Clínica Provida | julio.salazar@clinicaprovida.com.pe |
| Admin Atlántica | elki.villacorta@atlantica.com.pe |
| Admin Angel Divino Bus | hugo.tantajulca@angeldivinobus.com.pe |
| Técnico (Angel Divino) | renato.vega@angeldivinobus.com.pe |
| Solicitante (Angel Divino) | rosa.villanueva@angeldivinobus.com.pe |

Cambia las contraseñas antes de presentar o compartir el enlace.

---

## 1. Probar en Visual Studio Code (con XAMPP)

1. Abre XAMPP y enciende **MySQL**.
2. En phpMyAdmin crea la base `mesa_ayuda_ti` (cotejamiento `utf8mb4_unicode_ci`) e importa `database/mesa_ayuda_ti.sql`.
3. Abre la carpeta del proyecto en VS Code y en la terminal:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (en Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   python probar_db.py             # debe decir "¡Conexión exitosa!"
   python run.py
   ```
4. Entra a http://127.0.0.1:5000

El archivo `.env` ya viene listo para XAMPP (usuario `root` sin contraseña). Si tu MySQL tiene clave, cámbiala ahí.

## 2. Subir a PythonAnywhere

1. **Files**: sube el zip a `/home/jcachay/` y en una consola **Bash**:
   ```bash
   cd ~
   unzip mesa_ayuda_ti.zip
   cd mesa_ayuda_ti
   mv .env.pythonanywhere .env      # revisa/edita SECRET_KEY y JWT_SECRET
   pip3 install --user -r requirements.txt
   python3 probar_db.py
   python3 inicializar_bd.py        # BORRA y crea las tablas con los datos de ejemplo
   ```
2. **Web** > tu app:
   - *Source code*: `/home/jcachay/mesa_ayuda_ti`
   - Abre el *WSGI configuration file* y reemplaza su contenido por el de `wsgi_pythonanywhere.py`.
   - *Static files*: URL `/static/` → Directory `/home/jcachay/mesa_ayuda_ti/static`
3. Pulsa **Reload** y entra a `https://jcachay.pythonanywhere.com`.
   `/salud` te dice si la base de datos responde.

Si algo falla, mira el **Error log** en la pestaña Web.

## 3. Postman

Las rutas `/api_insertar_*` y `/api_obtener_*` siguen igual, pero ahora piden token:

1. `POST /api/login` con JSON `{"correo": "...", "password": "Clave123"}`
2. Copia `data.token` y en Postman: *Authorization → Bearer Token*.

El resto de la API REST está en `/api/docs` dentro del sistema.

## Estructura

```
run.py                 app principal (lo usa el WSGI)
config.py / db.py      configuración (.env) y conexión
auth.py                Módulo 1: login JWT, logout, roles, mi cuenta
usuarios.py            Módulo 1: CRUD de usuarios (admin / superusuario)
empresas.py            Superusuario: crear / editar / eliminar empresas
tickets.py             Módulos 2-4: tickets + fotos, asignación, estados, historial, SLA
notificaciones.py      Módulo 5: campana y notificaciones
dashboard.py           Módulo 6: dashboard, Excel, PDF
api_postman.py         Rutas de la colección de Postman (con JWT)
utils.py               hora de Perú, cálculo del SLA y formatos
database/              script SQL sin triggers
templates/ static/     vistas (Jinja) y estilos/JS
uploads/               fotos de evidencia (se crean solas)
```

## Reglas que antes hacían los triggers (ahora en Python)

- Correlativo por empresa (`EPS-0001`) con `SELECT ... FOR UPDATE`.
- `fecha_limite = creación + horas de la prioridad` (Alta 4 h, Media 24 h, Baja 72 h).
- Historial al crear, asignar, cambiar estado o comentar (comentario obligatorio).
- Notificaciones a administradores, técnico y solicitante.
- El correo de cada usuario debe usar el dominio de su empresa.
- La empresa siempre conserva al menos un administrador activo.
