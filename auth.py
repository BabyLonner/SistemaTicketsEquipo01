"""
MÓDULO 1 — Autenticación con JWT, roles y protección de rutas.

* El login genera un JWT (PyJWT, HS256) con: sub = id, rol, emp = empresa, jti.
  - En la web viaja en una cookie HttpOnly (mesa_token).
  - En la API (Postman) viaja en el header  Authorization: Bearer <token>.
* Cerrar sesión guarda el jti en tokens_revocados (el token deja de servir).
* Antes de cada petición se valida el token, que el usuario siga activo y
  que su empresa siga activa. Todas las rutas del sistema piden token válido.
* La empresa se identifica por el dominio del correo (empresa_dominios).
"""
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from db import conexion, consultar
from utils import ahora, dominio_de, entero

auth_bp = Blueprint("auth", __name__)

SQL_USUARIO = """
    SELECT u.id, u.nombre, u.correo, u.rol, u.activo, u.empresa_id, u.area_id,
           u.password_hash, a.nombre AS area,
           e.nombre AS empresa, e.codigo AS empresa_codigo, e.titulo_sistema,
           e.color_primario, e.color_secundario, e.prefijo_ticket,
           COALESCE(e.activo, 1) AS empresa_activa
      FROM users u
      LEFT JOIN empresas e ON e.id = u.empresa_id
      LEFT JOIN areas a    ON a.id = u.area_id
"""


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


def leer_token_de_peticion():
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return request.cookies.get(config.COOKIE_TOKEN)


def es_peticion_api():
    return request.path.startswith("/api") or request.path.startswith("/api_")


@auth_bp.before_app_request
def cargar_usuario():
    """Valida el JWT de la petición y deja el usuario en g.usuario (o None)."""
    g.usuario = None
    g.jwt = None
    if request.endpoint == "static":
        return
    token = leer_token_de_peticion()
    if not token:
        return
    try:
        datos = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        g.error_token = "Tu sesión expiró. Vuelve a iniciar sesión."
        return
    except jwt.InvalidTokenError:
        g.error_token = "Token no válido."
        return
    if consultar("SELECT 1 FROM tokens_revocados WHERE jti = %s", (datos.get("jti"),), uno=True):
        g.error_token = "La sesión fue cerrada. Vuelve a iniciar sesión."
        return
    usuario = consultar(SQL_USUARIO + " WHERE u.id = %s", (entero(datos.get("sub")),), uno=True)
    if not usuario or not usuario["activo"] or not usuario["empresa_activa"]:
        g.error_token = "Tu cuenta o tu empresa está desactivada."
        return
    usuario.pop("password_hash", None)
    g.usuario = usuario
    g.jwt = datos


def _no_autorizado(mensaje, codigo):
    if es_peticion_api():
        return jsonify(status=-1, ok=False, message=mensaje, error=mensaje), codigo
    if codigo == 401:
        if request.method == "GET":
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        flash(mensaje, "error")
        return redirect(url_for("auth.login"))
    return render_template("error.html", codigo=403, mensaje=mensaje), 403


def login_requerido(vista):
    """Protege una ruta: exige un JWT válido (cookie o header Authorization)."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.get("usuario") is None:
            return _no_autorizado(g.get("error_token") or "Inicia sesión para continuar.", 401)
        return vista(*args, **kwargs)

    return envoltura


def roles_requeridos(*roles):
    """Decorador por rol:  @roles_requeridos('Administrador', 'Superusuario')"""

    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(*args, **kwargs):
            if g.usuario["rol"] not in roles:
                return _no_autorizado("Tu rol no tiene permiso para esta opción.", 403)
            return vista(*args, **kwargs)

        return envoltura

    return decorador


def es_super(usuario=None):
    usuario = usuario or g.get("usuario")
    return bool(usuario) and usuario["rol"] == "Superusuario"


def empresa_filtro():
    """Empresa que se está viendo: la del usuario, o la elegida por el superusuario (None = todas)."""
    if not g.get("usuario"):
        return None
    if es_super():
        return entero(session.get("empresa_filtro"))
    return g.usuario["empresa_id"]


# =====================================================================
#  Login / logout (web)
# =====================================================================
def _autenticar(correo, clave):
    """Devuelve (usuario, error)."""
    correo = (correo or "").strip().lower()
    if not correo or not clave:
        return None, "Ingresa tu correo y contraseña."
    usuario = consultar(SQL_USUARIO + " WHERE u.correo = %s", (correo,), uno=True)
    if not usuario or not clave_correcta(clave, usuario["password_hash"]):
        return None, "Correo o contraseña incorrectos."
    if not usuario["activo"]:
        return None, "Tu cuenta está desactivada. Pide al administrador de tu empresa que la active."
    if usuario["rol"] != "Superusuario":
        if not usuario["empresa_activa"]:
            return None, "Tu empresa está desactivada en el sistema."
        # La empresa se reconoce por el dominio del correo
        dominio_ok = consultar(
            "SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
            (usuario["empresa_id"], dominio_de(correo)), uno=True,
        )
        if not dominio_ok:
            return None, "El dominio de tu correo no corresponde a tu empresa."
    return usuario, None


def _registrar_acceso(usuario_id):
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET ultimo_acceso = %s WHERE id = %s", (ahora(), usuario_id))
    con.commit()


@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if g.get("usuario"):
        return redirect(url_for("dashboard.dashboard"))
    if request.method == "POST":
        usuario, error = _autenticar(request.form.get("correo"), request.form.get("clave", ""))
        if error:
            flash(error, "error")
            return render_template("login.html", correo=request.form.get("correo", "")), 401
        recordar = request.form.get("recordar") == "1"
        token, duracion = crear_token(usuario, recordar)
        _registrar_acceso(usuario["id"])
        session.clear()
        destino = request.args.get("next") or ""
        if not destino.startswith("/") or destino.startswith("//"):
            destino = url_for("dashboard.dashboard")
        respuesta = make_response(redirect(destino))
        respuesta.set_cookie(
            config.COOKIE_TOKEN, token,
            max_age=int(duracion.total_seconds()) if recordar else None,
            httponly=True, samesite="Lax", secure=request.is_secure,
        )
        return respuesta
    return render_template("login.html", correo="")


def _revocar_token_actual():
    datos = g.get("jwt")
    if not datos:
        return
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO tokens_revocados (jti, usuario_id, expira_en, created_at) VALUES (%s, %s, %s, %s)",
            (datos["jti"], entero(datos["sub"]),
             datetime.fromtimestamp(datos["exp"], timezone.utc).astimezone(timezone(timedelta(hours=-5))).replace(tzinfo=None),
             ahora()),
        )
        # Limpieza: los tokens ya vencidos no hace falta guardarlos
        cur.execute("DELETE FROM tokens_revocados WHERE expira_en < %s", (ahora(),))
    con.commit()


@auth_bp.route("/salir")
def logout():
    _revocar_token_actual()
    session.clear()
    respuesta = make_response(redirect(url_for("auth.login")))
    respuesta.delete_cookie(config.COOKIE_TOKEN)
    flash("Cerraste sesión correctamente.", "ok")
    return respuesta


# Alias de la ruta antigua
@auth_bp.route("/cerrar-sesion")
def cerrar_sesion():
    return logout()


@auth_bp.route("/empresa-activa", methods=["POST"])
@roles_requeridos("Superusuario")
def cambiar_empresa_activa():
    """Selector 'Empresa' de la cabecera (solo superusuario)."""
    session["empresa_filtro"] = entero(request.form.get("empresa_id"))
    destino = request.referrer or url_for("dashboard.dashboard")
    return redirect(destino)


@auth_bp.route("/cuenta", methods=["GET", "POST"])
@login_requerido
def cuenta():
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        repetir = request.form.get("repetir", "")
        fila = consultar("SELECT password_hash FROM users WHERE id = %s", (g.usuario["id"],), uno=True)
        error = None
        if not clave_correcta(actual, fila["password_hash"]):
            error = "La contraseña actual no es correcta."
        elif nueva != repetir:
            error = "Las contraseñas nuevas no coinciden."
        else:
            error = validar_clave_nueva(nueva)
        if error:
            flash(error, "error")
        else:
            con = conexion()
            with con.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashear(nueva), g.usuario["id"]))
            con.commit()
            flash("Contraseña actualizada.", "ok")
        return redirect(url_for("auth.cuenta"))
    return render_template("cuenta.html")


# =====================================================================
#  API (Postman): login / logout / usuario actual
# =====================================================================
@auth_bp.post("/api/login")
def api_login():
    datos = request.get_json(silent=True) or request.form
    usuario, error = _autenticar(datos.get("correo"), datos.get("password") or datos.get("clave", ""))
    if error:
        return jsonify(status=-1, message=error), 401
    token, duracion = crear_token(usuario, bool(datos.get("recordar")))
    _registrar_acceso(usuario["id"])
    return jsonify(
        status=1,
        message="Inicio de sesión correcto",
        data={
            "token": token,
            "tipo": "Bearer",
            "expira_en_segundos": int(duracion.total_seconds()),
            "usuario": {
                "id": usuario["id"], "nombre": usuario["nombre"], "correo": usuario["correo"],
                "rol": usuario["rol"], "empresa_id": usuario["empresa_id"], "empresa": usuario["empresa"],
            },
        },
    )


@auth_bp.post("/api/logout")
@login_requerido
def api_logout():
    _revocar_token_actual()
    return jsonify(status=1, message="Token invalidado")


@auth_bp.get("/api/yo")
@login_requerido
def api_yo():
    return jsonify(status=1, data=g.usuario)


@auth_bp.get("/api/empresa-por-correo")
def api_empresa_por_correo():
    """Muestra la identidad de la empresa en el login apenas se escribe el correo."""
    dominio = dominio_de(request.args.get("correo"))
    empresa = consultar(
        """SELECT e.nombre, e.titulo_sistema, e.color_primario, e.color_secundario
             FROM empresa_dominios d JOIN empresas e ON e.id = d.empresa_id
            WHERE d.dominio = %s AND e.activo = 1""",
        (dominio,), uno=True,
    ) if dominio else None
    return jsonify(empresa=empresa)
