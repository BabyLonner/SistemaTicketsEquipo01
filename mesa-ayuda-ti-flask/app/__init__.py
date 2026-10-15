import os

from flask import Flask, jsonify, render_template, request

from config import BASE_DIR, Config

from .extensions import bcrypt, db, jwt


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)

    from .auth import registrar_jwt
    registrar_jwt(app)

    from . import plantillas
    plantillas.registrar(app)

    from .web import web_bp
    from .api import api_bp
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    from .comandos import registrar_comandos
    registrar_comandos(app)

    _registrar_errores(app)

    with app.app_context():
        db.create_all()

    return app


def _registrar_errores(app):
    textos = {
        403: ("No tienes acceso a esta página", "Tu perfil no tiene permiso para ver esto."),
        404: ("No encontramos esta página", "Revisa la dirección o vuelve al inicio."),
        413: ("El archivo es demasiado grande", "Las fotos deben pesar menos de 5 MB cada una."),
        500: ("Algo falló en el servidor", "Inténtalo de nuevo en unos minutos."),
    }

    def manejar(error):
        codigo = getattr(error, "code", 500) or 500
        titulo, detalle = textos.get(codigo, textos[500])
        if request.path.startswith("/api/"):
            return jsonify(error=titulo), codigo
        return render_template("error.html", codigo=codigo, titulo=titulo, detalle=detalle), codigo

    for codigo in textos:
        app.register_error_handler(codigo, manejar)
