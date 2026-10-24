"""
MESA DE AYUDA TI — Sistema de gestión de tickets para las 6 empresas del grupo.
Archivo principal (local:  python run.py   |   PythonAnywhere: lo importa el WSGI).

Módulos:
  1 auth.py / usuarios.py / empresas.py   Autenticación JWT, roles, usuarios y empresas
  2-4 tickets.py                          Tickets + fotos, asignación/estados/historial, SLA
  5 notificaciones.py                     Campana y notificaciones internas
  6 dashboard.py                          Dashboard, Excel/PDF y API
  api_postman.py                          Rutas de la colección de Postman (con JWT)
"""
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

import config
from api_postman import api_postman_bp
from auth import auth_bp, es_super, empresa_filtro, login_requerido
from dashboard import dashboard_bp
from db import cerrar_conexion, consultar
from empresas import empresas_bp
from notificaciones import contar_no_leidas, notificaciones_bp
from tickets import tickets_bp
from usuarios import usuarios_bp
from utils import hace, iniciales, nombre_corto

app = Flask(__name__)
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
    JSON_SORT_KEYS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.json.ensure_ascii = False
app.json.sort_keys = False

for bp in (auth_bp, dashboard_bp, tickets_bp, usuarios_bp, empresas_bp, notificaciones_bp, api_postman_bp):
    app.register_blueprint(bp)

app.teardown_appcontext(cerrar_conexion)
app.jinja_env.filters["iniciales"] = iniciales
app.jinja_env.filters["hace"] = hace
app.jinja_env.filters["nombre_corto"] = nombre_corto

TEMA_GENERAL = {
    "titulo": "Mesa de Ayuda TI",
    "color_primario": "#3D4A8A",
    "color_secundario": "#DCE0F5",
}


@app.context_processor
def datos_globales():
    """Datos que usan todas las plantillas: usuario, identidad de la empresa y campana."""
    usuario = g.get("usuario")
    tema = dict(TEMA_GENERAL)
    contexto = {"usuario": usuario, "version": config.VERSION, "correo_soporte": config.CORREO_SOPORTE,
                "no_leidas": 0, "empresas_menu": [], "empresa_activa": None}
    if usuario:
        contexto["no_leidas"] = contar_no_leidas(usuario["id"])
        if es_super():
            contexto["empresas_menu"] = consultar("SELECT id, nombre, titulo_sistema, color_primario, color_secundario FROM empresas ORDER BY nombre")
            elegida = next((e for e in contexto["empresas_menu"] if e["id"] == empresa_filtro()), None)
            contexto["empresa_activa"] = elegida
            if elegida:
                tema = {"titulo": elegida["titulo_sistema"], "color_primario": elegida["color_primario"],
                        "color_secundario": elegida["color_secundario"]}
        else:
            tema = {"titulo": usuario["titulo_sistema"], "color_primario": usuario["color_primario"],
                    "color_secundario": usuario["color_secundario"]}
    contexto["tema"] = tema
    return contexto


@app.get("/ayuda")
@login_requerido
def ayuda():
    return render_template("ayuda.html")


@app.get("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@app.get("/salud")
def salud():
    """Comprueba que la app y la base de datos respondan (útil en PythonAnywhere)."""
    try:
        consultar("SELECT 1 AS ok", uno=True)
        return jsonify(ok=True, base_de_datos="conectada")
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=str(e)), 500


def _error(codigo, mensaje):
    if request.path.startswith("/api"):
        return jsonify(status=-1, ok=False, message=mensaje, error=mensaje), codigo
    return render_template("error.html", codigo=codigo, mensaje=mensaje), codigo


@app.errorhandler(404)
def no_encontrado(_e):
    return _error(404, "La página o el registro que buscas no existe, o no tienes acceso a él.")


@app.errorhandler(405)
def metodo_no_permitido(_e):
    return _error(405, "Esta acción no acepta ese tipo de petición.")


@app.errorhandler(RequestEntityTooLarge)
def demasiado_grande(_e):
    return _error(413, "Los archivos superan el tamaño total permitido (16 MB).")


@app.errorhandler(500)
def error_interno(_e):
    return _error(500, "Ocurrió un error inesperado. Inténtalo de nuevo en un momento.")


if __name__ == "__main__":
    app.run(debug=True)
