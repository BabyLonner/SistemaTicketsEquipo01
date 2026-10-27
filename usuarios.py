"""
MÓDULO 1 — Gestión de usuarios (Administrador de la empresa o Superusuario).

API que usa static/js/usuarios.js:
  GET  /api/usuarios                lista de la empresa + áreas + contadores
  POST /api/usuarios                registrar (contraseña temporal hasheada con bcrypt)
  PUT  /api/usuarios/<id>           editar nombre, correo, rol, área y restablecer contraseña
  POST /api/usuarios/<id>/estado    activar / desactivar

Reglas (antes eran triggers): el correo debe usar el dominio de la empresa,
nadie se desactiva a sí mismo y la empresa conserva al menos un administrador activo.
"""
from flask import Blueprint, g, jsonify, request

from auth import ROL_ADMIN, ROL_SUPER, empresa_actual, hashear, roles_requeridos, validar_clave_nueva
from db import conexion, consultar
from utils import ROLES_EMPRESA, ahora, correo_valido, dominio_de, entero

usuarios_bp = Blueprint("usuarios", __name__)

SQL_USUARIOS = """
    SELECT u.id, u.nombre, u.correo, u.rol, u.activo, u.empresa_id, u.area_id,
           e.nombre AS empresa, a.nombre AS area, u.created_at, u.ultimo_acceso
      FROM users u
      JOIN empresas e    ON e.id = u.empresa_id
      LEFT JOIN areas a  ON a.id = u.area_id
"""


def _json_usuario(u):
    return {
        "id": u["id"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"],
        "activo": bool(u["activo"]), "empresa_id": u["empresa_id"], "empresa": u["empresa"],
        "area_id": u["area_id"], "area": u["area"],
        "created_at": u["created_at"].strftime("%d/%m/%Y %H:%M") if u["created_at"] else None,
        "ultimo_acceso": u["ultimo_acceso"].strftime("%d/%m/%Y %H:%M") if u["ultimo_acceso"] else None,
    }


def _empresa():
    empresa_id = empresa_actual()
    if not empresa_id:
        return None, (jsonify(error="Elige primero la empresa que quieres administrar."), 403)
    return empresa_id, None


def _usuario_de_mi_empresa(usuario_id, empresa_id):
    return consultar(SQL_USUARIOS + " WHERE u.id = %s AND u.empresa_id = %s", (usuario_id, empresa_id), uno=True)


def _dominios(empresa_id):
    return [d["dominio"] for d in consultar("SELECT dominio FROM empresa_dominios WHERE empresa_id = %s", (empresa_id,))]


def _validar(datos, empresa_id, usuario_id=None, clave_obligatoria=True):
    errores = {}
    nombre = " ".join((datos.get("nombre") or "").split())
    correo = (datos.get("correo") or "").strip().lower()
    rol = datos.get("rol") or ""
    area_id = entero(datos.get("area_id"))
    clave = datos.get("clave") or ""
    if len(nombre) < 3:
        errores["nombre"] = "Ingresa el nombre completo."
    if not correo_valido(correo):
        errores["correo"] = "Ingresa un correo corporativo válido."
    elif dominio_de(correo) not in _dominios(empresa_id):
        errores["correo"] = "El correo debe terminar en " + ", ".join("@" + d for d in _dominios(empresa_id)) + "."
    elif consultar("SELECT 1 FROM users WHERE correo = %s AND id <> %s", (correo, usuario_id or 0), uno=True):
        errores["correo"] = "Ya existe un usuario con ese correo."
    if rol not in ROLES_EMPRESA:
        errores["rol"] = "Selecciona un rol."
    if area_id and not consultar("SELECT 1 FROM areas WHERE id = %s AND empresa_id = %s", (area_id, empresa_id), uno=True):
        errores["area_id"] = "El área no pertenece a la empresa."
    if clave or clave_obligatoria:
        error_clave = validar_clave_nueva(clave)
        if error_clave:
            errores["clave"] = error_clave
    return {"nombre": nombre, "correo": correo, "rol": rol, "area_id": area_id, "clave": clave}, errores


def _quedaria_sin_admin(usuario, nuevo_rol, nuevo_activo):
    if usuario["rol"] != ROL_ADMIN or not usuario["activo"]:
        return False
    if nuevo_rol == ROL_ADMIN and nuevo_activo:
        return False
    otros = consultar(
        "SELECT COUNT(*) AS n FROM users WHERE empresa_id = %s AND rol = %s AND activo = 1 AND id <> %s",
        (usuario["empresa_id"], ROL_ADMIN, usuario["id"]), uno=True)
    return otros["n"] == 0


@usuarios_bp.get("/api/usuarios")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def listar():
    empresa_id, error = _empresa()
    if error:
        return error
    usuarios = consultar(SQL_USUARIOS + " WHERE u.empresa_id = %s ORDER BY FIELD(u.rol, 'Administrador', 'Técnico', 'Solicitante'), u.nombre",
                         (empresa_id,))
    areas = consultar("SELECT id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre", (empresa_id,))
    empresa = consultar("SELECT id, nombre FROM empresas WHERE id = %s", (empresa_id,), uno=True)
    return jsonify(usuarios=[_json_usuario(u) for u in usuarios], areas=areas, empresa=empresa,
                   dominios=_dominios(empresa_id), yo=g.usuario_token["id"])


@usuarios_bp.post("/api/usuarios")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def crear():
    empresa_id, error = _empresa()
    if error:
        return error
    datos, errores = _validar(request.get_json(silent=True) or request.form, empresa_id)
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400
    con = conexion()
    with con.cursor() as cur:
        momento = ahora()
        cur.execute(
            """INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol, activo, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)""",
            (empresa_id, datos["area_id"], datos["nombre"], datos["correo"], hashear(datos["clave"]),
             datos["rol"], momento, momento),
        )
        nuevo = cur.lastrowid
    con.commit()
    return jsonify(mensaje=f"Usuario {datos['nombre']} registrado.",
                   usuario=_json_usuario(_usuario_de_mi_empresa(nuevo, empresa_id))), 201


@usuarios_bp.put("/api/usuarios/<int:usuario_id>")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def editar(usuario_id):
    empresa_id, error = _empresa()
    if error:
        return error
    usuario = _usuario_de_mi_empresa(usuario_id, empresa_id)
    if not usuario:
        return jsonify(error="El usuario no existe en tu empresa."), 404
    datos, errores = _validar(request.get_json(silent=True) or request.form, empresa_id, usuario_id, clave_obligatoria=False)
    if usuario_id == g.usuario_token["id"]:
        datos["rol"] = usuario["rol"]          # nadie se cambia su propio rol
    if not errores and _quedaria_sin_admin(usuario, datos["rol"], usuario["activo"]):
        errores["rol"] = "La empresa debe conservar al menos un administrador activo."
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET nombre = %s, correo = %s, rol = %s, area_id = %s, updated_at = %s WHERE id = %s",
                    (datos["nombre"], datos["correo"], datos["rol"], datos["area_id"], ahora(), usuario_id))
        if datos["clave"]:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashear(datos["clave"]), usuario_id))
    con.commit()
    mensaje = "Cambios guardados." + (" La contraseña fue restablecida." if datos["clave"] else "")
    return jsonify(mensaje=mensaje, usuario=_json_usuario(_usuario_de_mi_empresa(usuario_id, empresa_id)))


@usuarios_bp.post("/api/usuarios/<int:usuario_id>/estado")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def cambiar_estado(usuario_id):
    empresa_id, error = _empresa()
    if error:
        return error
    usuario = _usuario_de_mi_empresa(usuario_id, empresa_id)
    if not usuario:
        return jsonify(error="El usuario no existe en tu empresa."), 404
    if usuario_id == g.usuario_token["id"]:
        return jsonify(error="No puedes desactivar tu propia cuenta."), 400
    nuevo = 0 if usuario["activo"] else 1
    if _quedaria_sin_admin(usuario, usuario["rol"], nuevo):
        return jsonify(error="No puedes desactivar al único administrador activo de la empresa."), 400
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET activo = %s, updated_at = %s WHERE id = %s", (nuevo, ahora(), usuario_id))
    con.commit()
    return jsonify(mensaje=f"{usuario['nombre']} quedó {'activo' if nuevo else 'inactivo'}.",
                   usuario=_json_usuario(_usuario_de_mi_empresa(usuario_id, empresa_id)))
