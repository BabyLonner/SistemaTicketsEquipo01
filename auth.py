"""
MÓDULO 1 — Autenticación con JWT, roles y protección de rutas.

* Al iniciar sesión se genera un JWT (PyJWT, HS256) con sub = id, rol, emp y jti.
    - En la web viaja en una cookie HttpOnly (mesa_token).
    - En Postman viaja en el header  Authorization: Bearer <token>  (POST /api/login).
* Antes de CADA petición se valida el token: firma, vencimiento, que no esté
  en tokens_revocados, que el usuario siga activo y su empresa también.
  Si el token no es válido, la sesión de Flask se borra: la session solo
  guarda los datos que muestran las plantillas (nombre, rol, logo...).
* Cerrar sesión guarda el jti en tokens_revocados (el token deja de servir).
* Superusuario: no pertenece a ninguna empresa. Elige la empresa que quiere
  administrar en /empresas y dentro de ella actúa como administrador.
"""
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import g, jsonify, redirect, render_template, request, session, url_for

import config
from db import conexion, consultar
from utils import ahora, dominio_de
from vistas import V_USUARIOS_SESION

ROL_SUPER = "Superusuario"
ROL_ADMIN = "Administrador"
ROL_TECNICO = "Técnico"
ROL_SOLICITANTE = "Solicitante"


# =====================================================================
#  Contraseñas (bcrypt)
# =====================================================================
def hashear(clave):
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def clave_correcta(clave, hash_guardado):
    try:
        return bcrypt.checkpw(clave.encode("utf-8"), hash_guardado.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


def validar_clave_nueva(clave):
    if len(clave or "") < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not any(c.isdigit() for c in clave) or not any(c.isalpha() for c in clave):
        return "La contraseña debe combinar letras y números."
    return None


# =====================================================================
#  JWT
# =====================================================================
def crear_token(usuario, recordar=False):
    momento = datetime.now(timezone.utc)
    duracion = timedelta(days=config.JWT_DIAS_RECORDAR) if recordar else timedelta(hours=config.JWT_HORAS)
    payload = {
        "sub": str(usuario["id"]),
        "rol": usuario["rol"],
        "emp": usuario["empresa_id"],
        "jti": str(uuid.uuid4()),
        "iat": momento,
        "exp": momento + duracion,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256"), duracion


def _token_de_la_peticion():
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return request.cookies.get(config.COOKIE_TOKEN)


def autenticar(correo, clave):
    """Devuelve (usuario, error). La empresa se reconoce por el dominio del correo."""
    correo = (correo or "").strip().lower()
    if not correo or not clave:
        return None, "Ingresa tu correo y contraseña."
    usuario = consultar(f"SELECT * FROM {V_USUARIOS_SESION} AS v WHERE v.correo = %s", (correo,), uno=True)
    if not usuario or not clave_correcta(clave, usuario["password_hash"]):
        return None, "Correo o contraseña incorrectos."
    error = verificar_cuenta(usuario)
    return (None, error) if error else (usuario, None)


def verificar_cuenta(usuario):
    """Reglas comunes al login con contraseña y al login facial. Devuelve el error o None."""
    correo = usuario["correo"]
    if not usuario["activo"]:
        return "Tu cuenta está desactivada. Pide al administrador de tu empresa que la active."
    if usuario["rol"] != ROL_SUPER:
        if not usuario["empresa_activa"]:
            return "Tu empresa está desactivada en el sistema."
        dominio_ok = consultar(
            "SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
            (usuario["empresa_id"], dominio_de(correo)), uno=True,
        )
        if not dominio_ok:
            return "El dominio de tu correo no corresponde a tu empresa."
    return None


def llenar_sesion(usuario):
    """Datos que muestran las plantillas (base.html usa session.nombre, session.rol...)."""
    empresa_activa = session.get("empresa_activa") if usuario["rol"] == ROL_SUPER else None
    session["usuario_id"] = usuario["id"]
    session["nombre"] = usuario["nombre"]
    session["correo"] = usuario["correo"]
    session["rol"] = usuario["rol"]
    if usuario["rol"] == ROL_SUPER:
        empresa = consultar("SELECT * FROM empresas WHERE id = %s", (empresa_activa,), uno=True) if empresa_activa else None
        session["empresa_activa"] = empresa["id"] if empresa else None
        session["empresa_id"] = empresa["id"] if empresa else None
        session["empresa_nombre"] = empresa["nombre"] if empresa else "Todas las empresas"
        session["empresa_titulo"] = empresa["titulo_sistema"] if empresa else "Superusuario del sistema"
        session["empresa_logo"] = empresa["logo_url"] if empresa else None
        session["empresa_color"] = empresa["color_primario"] if empresa else None
        session["empresa_color2"] = empresa["color_secundario"] if empresa else None
    else:
        session["empresa_id"] = usuario["empresa_id"]
        session["empresa_nombre"] = usuario["empresa"]
        session["empresa_titulo"] = usuario["titulo_sistema"]
        session["empresa_logo"] = usuario["logo_url"]
        session["empresa_color"] = usuario["color_primario"]
        session["empresa_color2"] = usuario["color_secundario"]


def registrar_acceso(usuario_id):
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET ultimo_acceso = %s WHERE id = %s", (ahora(), usuario_id))
    con.commit()


def revocar_token_actual():
    datos = g.get("jwt")
    if not datos:
        return
    expira = datetime.fromtimestamp(datos["exp"], timezone.utc).astimezone(timezone(timedelta(hours=-5))).replace(tzinfo=None)
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO tokens_revocados (jti, usuario_id, expira_en, created_at) VALUES (%s, %s, %s, %s)",
            (datos["jti"], int(datos["sub"]), expira, ahora()),
        )
        cur.execute("DELETE FROM tokens_revocados WHERE expira_en < %s", (ahora(),))
    con.commit()


def validar_peticion():
    """before_request: el JWT manda. Sin token válido no hay sesión."""
    g.jwt = None
    g.usuario_token = None
    g.error_token = None
    if request.endpoint == "static":
        return
    token = _token_de_la_peticion()
    if not token:
        if session.get("usuario_id"):
            session.clear()
        return
    try:
        datos = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        usuario = None
        if not consultar("SELECT 1 FROM tokens_revocados WHERE jti = %s", (datos.get("jti"),), uno=True):
            usuario = consultar(f"SELECT * FROM {V_USUARIOS_SESION} AS v WHERE v.id = %s", (int(datos["sub"]),), uno=True)
        if not usuario or not usuario["activo"] or not usuario["empresa_activa"]:
            raise jwt.InvalidTokenError("revocado o inactivo")
    except jwt.ExpiredSignatureError:
        g.error_token = "Tu sesión expiró. Vuelve a iniciar sesión."
        session.clear()
        return
    except (jwt.InvalidTokenError, ValueError, KeyError):
        g.error_token = "La sesión ya no es válida. Vuelve a iniciar sesión."
        session.clear()
        return
    usuario.pop("password_hash", None)
    g.jwt = datos
    g.usuario_token = usuario
    if session.get("usuario_id") != usuario["id"] or session.get("rol") != usuario["rol"]:
        if session.get("usuario_id") != usuario["id"]:
            session.clear()
        llenar_sesion(usuario)


def es_api():
    return request.path.startswith("/api")


def _no_autorizado(mensaje, codigo):
    if es_api():
        return jsonify(status=-1, ok=False, error=mensaje, message=mensaje), codigo
    if codigo == 401:
        return redirect(url_for("inicio"))
    return render_template("error.html", codigo=codigo, mensaje=mensaje), codigo


def login_requerido(vista):
    """Pide un JWT válido (cookie o header Authorization)."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not g.get("usuario_token"):
            return _no_autorizado(g.get("error_token") or "Inicia sesión para continuar.", 401)
        return vista(*args, **kwargs)
    return envoltura


def roles_requeridos(*roles):
    """@roles_requeridos('Administrador', 'Superusuario')"""
    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(*args, **kwargs):
            if g.usuario_token["rol"] not in roles:
                return _no_autorizado("Tu rol no tiene permiso para esta opción.", 403)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def es_super():
    return bool(g.get("usuario_token")) and g.usuario_token["rol"] == ROL_SUPER


def empresa_actual():
    """Empresa con la que se trabaja: la del usuario o la elegida por el superusuario."""
    if not g.get("usuario_token"):
        return None
    if es_super():
        return session.get("empresa_activa")
    return g.usuario_token["empresa_id"]
