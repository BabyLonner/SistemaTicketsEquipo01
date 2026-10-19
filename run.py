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
