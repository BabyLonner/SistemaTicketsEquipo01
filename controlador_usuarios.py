import re

import bcrypt

from bd import obtenerconexion
from utilidades import AREAS, EMPRESAS, ROLES, ErrorNegocio, ahora, iniciales

PATRON_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
COLUMNAS = "id, nombre, email, rol, empresa, area, activo, created_at"


def encriptar_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_correcto(password, hash_guardado):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def _completar(usuario):
    if usuario:
        usuario["activo"] = bool(usuario["activo"])
        usuario["iniciales"] = iniciales(usuario["nombre"])
        usuario["primer_nombre"] = usuario["nombre"].split()[0]
    return usuario


def a_json(usuario):
    return {"id": usuario["id"], "nombre": usuario["nombre"], "email": usuario["email"], "rol": usuario["rol"],
            "empresa": usuario["empresa"], "area": usuario["area"], "activo": usuario["activo"],
            "created_at": usuario["created_at"].isoformat()}


def obtener_por_id(usuario_id):
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT " + COLUMNAS + " FROM users WHERE id = %s", (usuario_id,))
            return _completar(cursor.fetchone())


def verificar_credenciales(email, password):
    """Devuelve el usuario si el correo y la contraseña son correctos; si no, None."""
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT " + COLUMNAS + ", password FROM users WHERE email = %s", (email.strip().lower(),))
            usuario = cursor.fetchone()
    if usuario is None or not password_correcto(password, usuario["password"]):
        return None
    del usuario["password"]
    return _completar(usuario)


def listar(q="", rol="", estado="", empresa=""):
    sql = "SELECT " + COLUMNAS + " FROM users WHERE 1 = 1"
    parametros = []
    if q:
        sql += " AND (LOWER(nombre) LIKE %s OR LOWER(email) LIKE %s)"
        parametros += ["%" + q.lower() + "%", "%" + q.lower() + "%"]
    if rol in ROLES:
        sql += " AND rol = %s"
        parametros.append(rol)
    if estado in ("activo", "inactivo"):
        sql += " AND activo = %s"
        parametros.append(1 if estado == "activo" else 0)
    if empresa:
        sql += " AND empresa = %s"
        parametros.append(empresa)
    sql += " ORDER BY nombre"

    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return [_completar(u) for u in cursor.fetchall()]


def listar_tecnicos(solo_activos=False):
    sql = "SELECT " + COLUMNAS + " FROM users WHERE rol = 'Técnico'"
    if solo_activos:
        sql += " AND activo = 1"
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql + " ORDER BY nombre")
            return [_completar(u) for u in cursor.fetchall()]


def _activo(valor, defecto=True):
    if valor is None:
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).lower() in ("1", "true", "on", "si", "sí")


def validar(datos, usuario_id=None):
    errores = {}
    nombre = (datos.get("nombre") or "").strip()
    email = (datos.get("email") or "").strip().lower()
    password = datos.get("password") or ""
    rol = datos.get("rol") or ""
    empresa = datos.get("empresa") or ""
    area = datos.get("area") or ""

    if len(nombre) < 3:
        errores["nombre"] = "Escribe el nombre completo."
    if not PATRON_EMAIL.match(email):
        errores["email"] = "Escribe un correo válido."
    else:
        conexion = obtenerconexion()
        with conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (email, usuario_id or 0))
                if cursor.fetchone():
                    errores["email"] = "Ya existe un usuario con ese correo."
    if (usuario_id is None or password) and len(password) < 8:
        errores["password"] = "La contraseña debe tener al menos 8 caracteres."
    if rol not in ROLES:
        errores["rol"] = "Elige un rol."
    if empresa not in EMPRESAS:
        errores["empresa"] = "Elige una empresa."
    if area and area not in AREAS:
        errores["area"] = "Elige un área válida."
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)
    return {"nombre": nombre, "email": email, "password": password, "rol": rol, "empresa": empresa,
            "area": area or None, "activo": _activo(datos.get("activo"))}


def crear(datos):
    limpio = validar(datos)
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            sql = ("INSERT INTO users (nombre, email, password, rol, empresa, area, activo, created_at) "
                   "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
            cursor.execute(sql, (limpio["nombre"], limpio["email"], encriptar_password(limpio["password"]),
                                 limpio["rol"], limpio["empresa"], limpio["area"], int(limpio["activo"]), ahora()))
            nuevo_id = cursor.lastrowid
        conexion.commit()
    return obtener_por_id(nuevo_id)


def actualizar(usuario_id, datos, actor):
    limpio = validar(datos, usuario_id)
    limpio["activo"] = _activo(datos.get("activo"), True)
    if usuario_id == actor["id"] and (limpio["rol"] != "Administrador" or not limpio["activo"]):
        raise ErrorNegocio("No puedes quitarte el rol de administrador ni desactivar tu propia cuenta.", 409)

    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            sql = "UPDATE users SET nombre = %s, email = %s, rol = %s, empresa = %s, area = %s, activo = %s WHERE id = %s"
            cursor.execute(sql, (limpio["nombre"], limpio["email"], limpio["rol"], limpio["empresa"], limpio["area"],
                                 int(limpio["activo"]), usuario_id))
            if limpio["password"]:
                cursor.execute("UPDATE users SET password = %s WHERE id = %s",
                               (encriptar_password(limpio["password"]), usuario_id))
        conexion.commit()
    return obtener_por_id(usuario_id)


def cambiar_activo(usuario_id, activo, actor):
    if usuario_id == actor["id"]:
        raise ErrorNegocio("No puedes desactivar tu propia cuenta.", 409)
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("UPDATE users SET activo = %s WHERE id = %s", (int(activo), usuario_id))
        conexion.commit()
    return obtener_por_id(usuario_id)
