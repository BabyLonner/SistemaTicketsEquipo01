from datetime import timedelta
from functools import wraps

from flask import abort, flash, g, jsonify, redirect, request, url_for
from flask_jwt_extended import (JWTManager, create_access_token, get_current_user, get_jwt,
                                verify_jwt_in_request)
from flask_jwt_extended.exceptions import CSRFError, JWTExtendedException
from jwt.exceptions import PyJWTError

import controlador_usuarios
from bd import obtenerconexion
from utilidades import ahora

jwt = JWTManager()

DURACION_TOKEN = timedelta(hours=8)
DURACION_RECORDAR = timedelta(days=7)


def configurar_jwt(app):
    # La web guarda el token en una cookie HttpOnly; la API lo recibe en el header Authorization
    app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = DURACION_TOKEN
    app.config["JWT_COOKIE_SECURE"] = False      # pon True cuando uses HTTPS
    app.config["JWT_COOKIE_SAMESITE"] = "Lax"
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_CSRF_CHECK_FORM"] = True     # los formularios envían el campo csrf_token
    jwt.init_app(app)

    @jwt.user_lookup_loader
    def cargar_usuario(_header, datos):
        return controlador_usuarios.obtener_por_id(int(datos["sub"]))

    @jwt.token_in_blocklist_loader
    def token_revocado(_header, datos):
        conexion = obtenerconexion()
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT id FROM tokens_revocados WHERE jti = %s", (datos["jti"],))
                return cursor.fetchone() is not None


def crear_token(usuario, recordar=False):
    """Devuelve (token, max_age de la cookie)."""
    duracion = DURACION_RECORDAR if recordar else DURACION_TOKEN
    token = create_access_token(identity=str(usuario["id"]), expires_delta=duracion,
                                additional_claims={"rol": usuario["rol"]})
    return token, int(duracion.total_seconds()) if recordar else None


def revocar_token_actual():
    """Cierre de sesión: el token queda en la lista de revocados y ya no sirve."""
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO tokens_revocados (jti, created_at) VALUES (%s, %s)", (get_jwt()["jti"], ahora()))
        conexion.commit()


def es_api():
    return request.path.startswith("/api/")


def _sin_sesion(error):
    if es_api():
        if isinstance(error, CSRFError):
            return jsonify(error="Falta el encabezado X-CSRF-TOKEN."), 401
        return jsonify(error="Falta el token o no es válido."), 401
    if isinstance(error, CSRFError):
        flash("No pudimos verificar el formulario. Inténtalo de nuevo.", "error")
        return redirect(request.referrer or url_for("dashboard"))
    if request.method == "GET":
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    flash("Tu sesión terminó. Vuelve a ingresar.", "error")
    return redirect(url_for("login"))


def requiere_sesion(*roles):
    """Decorador de protección por rol.

    @requiere_sesion()                    cualquier usuario con sesión
    @requiere_sesion("Administrador")     solo administradores
    """
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            try:
                verify_jwt_in_request(locations=None if es_api() else ["cookies"])
                usuario = get_current_user()
            except (JWTExtendedException, PyJWTError) as error:
                return _sin_sesion(error)

            if usuario is None or not usuario["activo"]:
                return _sin_sesion(None)

            g.usuario = usuario
            if roles and usuario["rol"] not in roles:
                if es_api():
                    return jsonify(error="No tienes permiso para esta acción."), 403
                abort(403)
            return funcion(*args, **kwargs)
        return envoltura
    return decorador
