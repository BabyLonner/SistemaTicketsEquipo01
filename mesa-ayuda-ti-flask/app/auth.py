"""Autenticación con JWT y decorador de protección por rol (módulo 1)."""
from functools import wraps

from flask import abort, current_app, flash, g, jsonify, redirect, request, url_for
from flask_jwt_extended import create_access_token, get_current_user, get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import CSRFError, JWTExtendedException
from jwt.exceptions import PyJWTError

from .extensions import db, jwt
from .models import TokenRevocado, Usuario


def registrar_jwt(app):
    @jwt.user_lookup_loader
    def cargar_usuario(_header, datos):
        return db.session.get(Usuario, int(datos["sub"]))

    @jwt.token_in_blocklist_loader
    def token_revocado(_header, datos):
        return db.session.query(TokenRevocado.id).filter_by(jti=datos["jti"]).first() is not None


def es_api():
    return request.path.startswith("/api/")


def emitir_token(usuario, recordar=False):
    """Crea el token JWT. Devuelve (token, max_age de la cookie o None)."""
    duracion = current_app.config["JWT_TOKEN_RECORDAR"] if recordar else current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    token = create_access_token(identity=str(usuario.id), expires_delta=duracion,
                                additional_claims={"rol": usuario.rol})
    return token, int(duracion.total_seconds()) if recordar else None


def revocar_token_actual():
    """Invalida el token en uso guardando su jti en la lista de revocados."""
    db.session.add(TokenRevocado(jti=get_jwt()["jti"]))
    db.session.commit()


def _sin_sesion(error):
    if es_api():
        mensaje = "Falta el token o no es válido." if not isinstance(error, CSRFError) else "Falta el encabezado X-CSRF-TOKEN."
        return jsonify(error=mensaje), 401
    if isinstance(error, CSRFError):
        flash("No pudimos verificar el formulario. Inténtalo de nuevo.", "error")
        return redirect(request.referrer or url_for("web.dashboard"))
    if request.method == "GET":
        return redirect(url_for("web.login", next=request.full_path.rstrip("?")))
    flash("Tu sesión terminó. Vuelve a ingresar.", "error")
    return redirect(url_for("web.login"))


def protegido(*roles):
    """Decorador: exige sesión válida y, si se indican, uno de los roles.

    Uso:  @protegido()                      -> cualquier usuario con sesión
          @protegido("Administrador")       -> solo administradores
    """
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            try:
                # La web usa la cookie; la API acepta el header Authorization o la cookie
                verify_jwt_in_request(locations=None if es_api() else ["cookies"])
                usuario = get_current_user()
            except (JWTExtendedException, PyJWTError) as error:
                return _sin_sesion(error)

            if usuario is None or not usuario.activo:
                return _sin_sesion(None)

            g.usuario = usuario
            if roles and usuario.rol not in roles:
                if es_api():
                    return jsonify(error="No tienes permiso para esta acción."), 403
                abort(403)
            return funcion(*args, **kwargs)
        return envoltura
    return decorador
