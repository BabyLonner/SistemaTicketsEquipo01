
import os

import bcrypt
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from db import obtener_conexion

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "clave-local-solo-desarrollo",
)


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")

        if not correo or not clave:
            flash("Ingresa tu correo y contraseña.", "error")
            return redirect(url_for("inicio"))

        conexion = obtener_conexion()

        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, empresa_id, nombre, correo,
                           password_hash, rol, activo
                    FROM users
                    WHERE correo = %s
                    LIMIT 1
                    """,
                    (correo,),
                )
                usuario = cursor.fetchone()

            if not usuario or not usuario["activo"]:
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))

            hash_guardado = usuario["password_hash"].encode("utf-8")

            if not bcrypt.checkpw(clave.encode("utf-8"), hash_guardado):
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))

            session.clear()
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["nombre"] = usuario["nombre"]
            session["correo"] = usuario["correo"]
            session["rol"] = usuario["rol"]

            with conexion.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET ultimo_acceso = NOW() WHERE id = %s",
                    (usuario["id"],),
                )
            conexion.commit()

            return redirect(url_for("dashboard"))

        except Exception:
            app.logger.exception("Error durante el inicio de sesión")
            flash("No se pudo completar el acceso. Inténtalo nuevamente.", "error")
            return redirect(url_for("inicio"))

        finally:
            conexion.close()

    if session.get("usuario_id"):
        return redirect(url_for("dashboard"))

    return render_template("index.html")


def obtener_datos_dashboard(empresa_id):
    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,
                    COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,
                    COALESCE(
                        SUM(
                            estado NOT IN ('Resuelto', 'Cerrado')
                            AND fecha_limite IS NOT NULL
                            AND fecha_limite < NOW()
                        ), 0
                    ) AS vencidos
                FROM tickets
                WHERE empresa_id = %s
            """, (empresa_id,))
            kpis = cursor.fetchone()

            cursor.execute(
                """
                SELECT estado, COUNT(*) AS total
                FROM tickets
                WHERE empresa_id = %s
                GROUP BY estado
                """,
                (empresa_id,),
            )
            estados = cursor.fetchall()

            cursor.execute(
                """
                SELECT p.nombre AS prioridad, COUNT(*) AS total
                FROM tickets t
                JOIN prioridades p ON p.id = t.prioridad_id
                WHERE t.empresa_id = %s
                GROUP BY p.id, p.nombre, p.nivel
                ORDER BY p.nivel DESC
                """,
                (empresa_id,),
            )
            prioridades = cursor.fetchall()

            cursor.execute(
                """
                SELECT u.nombre AS tecnico, COUNT(t.id) AS total
                FROM tickets t
                LEFT JOIN users u ON u.id = t.tecnico_id
                WHERE t.empresa_id = %s
                  AND t.tecnico_id IS NOT NULL
                GROUP BY u.id, u.nombre
                ORDER BY total DESC
                LIMIT 8
                """,
                (empresa_id,),
            )
            tecnicos = cursor.fetchall()

            cursor.execute(
                """
                SELECT c.nombre AS categoria, COUNT(*) AS total
                FROM tickets t
                JOIN categorias c ON c.id = t.categoria_id
                WHERE t.empresa_id = %s
                GROUP BY c.id, c.nombre
                ORDER BY total DESC
                """,
                (empresa_id,),
            )
            categorias = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    t.id,
                    t.asunto,
                    t.estado,
                    t.created_at,
                    p.nombre AS prioridad,
                    u.nombre AS tecnico
                FROM tickets t
                JOIN prioridades p ON p.id = t.prioridad_id
                LEFT JOIN users u ON u.id = t.tecnico_id
                WHERE t.empresa_id = %s
                ORDER BY t.created_at DESC
                LIMIT 5
                """,
                (empresa_id,),
            )
            recientes = cursor.fetchall()

        return {
            "kpis": kpis,
            "estados": estados,
            "prioridades": prioridades,
            "tecnicos": tecnicos,
            "categorias": categorias,
            "recientes": recientes,
        }
    finally:
        conexion.close()


@app.route("/dashboard")
def dashboard():
    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))

    datos = obtener_datos_dashboard(session["empresa_id"])

    return render_template(
        "dashboard.html",
        usuario_nombre=session["nombre"],
        usuario_rol=session["rol"],
        datos=datos,
    )


@app.route("/cerrar-sesion")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("inicio"))


if __name__ == "__main__":
    app.run(debug=True)
"""
Mesa de Ayuda TI — servidor Flask del proyecto.

    pip install -r requirements.txt
    python run.py            ->  http://127.0.0.1:5000

Antes, ejecutar tickets.sql en MySQL.
Variables de entorno opcionales (si no se definen se usan estos valores):
    DB_HOST=localhost  DB_PORT=3306  DB_USER=root  DB_PASSWORD=  DB_NAME=sistema_tickets
"""
import os

from flask import Flask, abort, redirect, render_template
from flask_jwt_extended import JWTManager
from jinja2 import TemplateNotFound

from tickets import tickets_bp

app = Flask(__name__)
app.config.update(
    DB_HOST=os.getenv("DB_HOST", "localhost"),
    DB_PORT=int(os.getenv("DB_PORT", "3306")),
    DB_USER=os.getenv("DB_USER", "root"),
    DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
    DB_NAME=os.getenv("DB_NAME", "sistema_tickets"),
    JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "cambiar-esta-clave-en-produccion-2026"),
    # Mientras el login con JWT (módulo de usuarios) no esté conectado, las
    # peticiones sin token usan este usuario. Quitar cuando el login funcione.
    # 1 = Juan Pérez (Solicitante), 2 = Luis Ramos (Técnico), 3 = Ana Díaz (Administrador)
    TICKETS_USUARIO_DEMO=int(os.getenv("TICKETS_USUARIO_DEMO", "1")),
)
JWTManager(app)

# ---- Módulos del sistema ----
app.register_blueprint(tickets_bp)      # Tickets: registro con evidencias


# ---- Pantallas (templates/) ----
@app.get("/")
def inicio():
    return render_template("index.html")


@app.get("/<pagina>.html")
def pantalla(pagina):
    try:
        return render_template(f"{pagina}.html")
    except TemplateNotFound:
        abort(404)


@app.get("/dev/usar/<int:usuario_id>")
def usar_usuario_demo(usuario_id):
    """Solo pruebas: /dev/usar/2 actúa como técnico, /dev/usar/3 como administrador."""
    app.config["TICKETS_USUARIO_DEMO"] = usuario_id
    return redirect("/tickets.html")


if __name__ == "__main__":
    app.run(debug=True)
