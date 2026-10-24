"""
Rutas de la colección de Postman (mismas URL y misma respuesta {status, data, message}).

AHORA PIDEN TOKEN: primero haz POST /api/login con
    {"correo": "superadmin@mesadeayuda.com.pe", "password": "Clave123"}
y en cada petición agrega el header:
    Authorization: Bearer <token>

Además respetan la empresa del token: un administrador solo ve y crea datos
de su empresa; las tablas globales (empresas, categorías, prioridades,
tokens) solo las modifica el superusuario.
"""
import uuid

from flask import Blueprint, g, jsonify, request

from auth import es_super, hashear, login_requerido, roles_requeridos
from db import conexion, consultar
from utils import ROLES_EMPRESA, ahora, correo_valido, dominio_de, entero, fecha_iso

api_postman_bp = Blueprint("api_postman", __name__)


def ok(data=None, mensaje="OK", codigo=200):
    return jsonify(status=1, data=data if data is not None else {}, message=mensaje), codigo


def error(mensaje, codigo=400):
    return jsonify(status=-1, data={}, message="Error: " + mensaje), codigo


def cuerpo():
    return request.get_json(silent=True) or request.form or {}


def ejecutar(sql, params):
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute(sql, params)
            nuevo = cur.lastrowid
        con.commit()
        return nuevo
    except Exception:
        con.rollback()
        raise


def serializar(filas):
    for f in filas:
        for k, v in list(f.items()):
            if hasattr(v, "isoformat"):
                f[k] = fecha_iso(v)
        f.pop("password_hash", None)
    return filas


def empresa_de_peticion(datos):
    """El superusuario elige la empresa; los demás usan SIEMPRE la de su token."""
    return entero(datos.get("empresa_id")) if es_super() else g.usuario["empresa_id"]


@api_postman_bp.errorhandler(Exception)
def _cualquier_error(e):
    from werkzeug.exceptions import HTTPException

    if isinstance(e, HTTPException):
        return e
    return error(repr(e), 500)


# ------------------------------------------------------------------ empresas
@api_postman_bp.post("/api_insertar_empresa")
@roles_requeridos("Superusuario")
def api_insertar_empresa():
    d = cuerpo()
    nuevo = ejecutar(
        """INSERT INTO empresas (codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema,
                                 color_primario, color_secundario, activo, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (d["codigo"], d["nombre"], d.get("razon_social"), d.get("ruc"), d["prefijo_ticket"], d["titulo_sistema"],
         d["color_primario"], d["color_secundario"], d.get("activo", 1), ahora()),
    )
    return ok({"id": nuevo}, "Empresa insertada correctamente")


@api_postman_bp.get("/api_obtener_empresas")
@login_requerido
def api_obtener_empresas():
    sql = "SELECT id, codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema, color_primario, color_secundario, ultimo_ticket, activo, created_at FROM empresas"
    filas = consultar(sql) if es_super() else consultar(sql + " WHERE id = %s", (g.usuario["empresa_id"],))
    return ok(serializar(filas), "Empresas obtenidas correctamente")


@api_postman_bp.post("/api_insertar_empresa_dominio")
@roles_requeridos("Superusuario")
def api_insertar_empresa_dominio():
    d = cuerpo()
    nuevo = ejecutar("INSERT INTO empresa_dominios (empresa_id, dominio) VALUES (%s, %s)",
                     (d["empresa_id"], d["dominio"].strip().lower().lstrip("@")))
    return ok({"id": nuevo}, "Dominio insertado correctamente")


@api_postman_bp.get("/api_obtener_empresa_dominios")
@login_requerido
def api_obtener_empresa_dominios():
    sql = "SELECT id, empresa_id, dominio FROM empresa_dominios"
    filas = consultar(sql) if es_super() else consultar(sql + " WHERE empresa_id = %s", (g.usuario["empresa_id"],))
    return ok(filas, "Dominios obtenidos correctamente")


# ------------------------------------------------------------------ áreas
@api_postman_bp.post("/api_insertar_area")
@roles_requeridos("Superusuario", "Administrador")
def api_insertar_area():
    d = cuerpo()
    empresa_id = empresa_de_peticion(d)
    nuevo = ejecutar("INSERT INTO areas (empresa_id, nombre, activo) VALUES (%s, %s, %s)",
                     (empresa_id, d["nombre"], d.get("activo", 1)))
    return ok({"id": nuevo, "empresa_id": empresa_id, "nombre": d["nombre"]}, "Area insertada correctamente")


@api_postman_bp.get("/api_obtener_areas")
@login_requerido
def api_obtener_areas():
    sql = "SELECT id, empresa_id, nombre, activo FROM areas"
    filas = consultar(sql + " ORDER BY id") if es_super() else consultar(
        sql + " WHERE empresa_id = %s ORDER BY id", (g.usuario["empresa_id"],))
    return ok(filas, "Areas obtenidas correctamente")


# ------------------------------------------------------------------ usuarios
@api_postman_bp.post("/api_insertar_user")
@roles_requeridos("Superusuario", "Administrador")
def api_insertar_user():
    d = cuerpo()
    empresa_id = empresa_de_peticion(d)
    correo = (d.get("correo") or "").strip().lower()
    rol = d.get("rol", "Solicitante")
    if rol not in ROLES_EMPRESA:
        return error("rol no válido (Administrador, Técnico o Solicitante)")
    if not correo_valido(correo) or not consultar(
            "SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
            (empresa_id, dominio_de(correo)), uno=True):
        return error("el correo debe usar el dominio de la empresa")
    # Acepta "password" (texto, se hashea aquí) o "password_hash" (ya en bcrypt)
    if d.get("password"):
        password_hash = hashear(d["password"])
    elif str(d.get("password_hash", "")).startswith("$2"):
        password_hash = d["password_hash"]
    else:
        return error("envía password (texto) o password_hash (bcrypt)")
    momento = ahora()
    nuevo = ejecutar(
        """INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol, activo, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (empresa_id, d.get("area_id"), d["nombre"], correo, password_hash, rol, d.get("activo", 1), momento, momento),
    )
    return ok({"id": nuevo, "empresa_id": empresa_id, "nombre": d["nombre"], "correo": correo, "rol": rol},
              "Usuario insertado correctamente")


@api_postman_bp.get("/api_obtener_users")
@roles_requeridos("Superusuario", "Administrador")
def api_obtener_users():
    sql = "SELECT id, empresa_id, area_id, nombre, correo, rol, activo, ultimo_acceso, created_at, updated_at FROM users"
    filas = consultar(sql + " ORDER BY id") if es_super() else consultar(
        sql + " WHERE empresa_id = %s ORDER BY id", (g.usuario["empresa_id"],))
    return ok(serializar(filas), "Usuarios obtenidos correctamente")


# ------------------------------------------------------------------ tokens
@api_postman_bp.post("/api_insertar_token_revocado")
@roles_requeridos("Superusuario")
def api_insertar_token_revocado():
    d = cuerpo()
    jti = d.get("jti") or str(uuid.uuid4())
    nuevo = ejecutar("INSERT INTO tokens_revocados (jti, usuario_id, expira_en, created_at) VALUES (%s, %s, %s, %s)",
                     (jti, d.get("usuario_id"), d.get("expira_en"), ahora()))
    return ok({"id": nuevo, "jti": jti}, "Token revocado insertado correctamente")


@api_postman_bp.get("/api_obtener_tokens_revocados")
@roles_requeridos("Superusuario")
def api_obtener_tokens_revocados():
    return ok(serializar(consultar("SELECT id, jti, usuario_id, expira_en, created_at FROM tokens_revocados")),
              "Tokens revocados obtenidos correctamente")


# ------------------------------------------------------------------ catálogos
@api_postman_bp.post("/api_insertar_categoria")
@roles_requeridos("Superusuario")
def api_insertar_categoria():
    d = cuerpo()
    nuevo = ejecutar("INSERT INTO categorias (nombre, descripcion, activo) VALUES (%s, %s, %s)",
                     (d["nombre"], d.get("descripcion"), d.get("activo", 1)))
    return ok({"id": nuevo}, "Categoría insertada correctamente")


@api_postman_bp.get("/api_obtener_categorias")
@login_requerido
def api_obtener_categorias():
    return ok(consultar("SELECT id, nombre, descripcion, activo FROM categorias"), "Categorías obtenidas correctamente")


@api_postman_bp.post("/api_insertar_prioridad")
@roles_requeridos("Superusuario")
def api_insertar_prioridad():
    d = cuerpo()
    ejecutar("INSERT INTO prioridades (id, nombre, sla_horas, nivel) VALUES (%s, %s, %s, %s)",
             (d["id"], d["nombre"], d["sla_horas"], d["nivel"]))
    return ok({"id": d["id"]}, "Prioridad insertada correctamente")


@api_postman_bp.get("/api_obtener_prioridades")
@login_requerido
def api_obtener_prioridades():
    return ok(consultar("SELECT id, nombre, sla_horas, nivel FROM prioridades ORDER BY nivel DESC"),
              "Prioridades obtenidas correctamente")


# ------------------------------------------------------------------ tickets
@api_postman_bp.post("/api_insertar_ticket")
@login_requerido
def api_insertar_ticket():
    """El solicitante es SIEMPRE el usuario del token (no se toma del JSON)."""
    from tickets import ErrorRegla, crear_ticket, fotos_de_la_peticion, obtener_ticket, validar_datos_ticket

    datos, errores = validar_datos_ticket(cuerpo())
    if errores:
        return error("; ".join(errores.values()))
    try:
        ticket_id = crear_ticket(g.usuario, datos, fotos_de_la_peticion())
    except ErrorRegla as e:
        return error(str(e))
    t = obtener_ticket(ticket_id, g.usuario)
    return ok({"id": ticket_id, "codigo": t["codigo"]}, "Ticket insertado correctamente")


@api_postman_bp.get("/api_obtener_tickets")
@login_requerido
def api_obtener_tickets():
    from tickets import buscar_tickets, ticket_json

    empresa_id = entero(request.args.get("empresa_id")) if es_super() else None
    return ok([ticket_json(t) for t in buscar_tickets(g.usuario, {}, empresa_id)], "Tickets obtenidos correctamente")


@api_postman_bp.post("/api_insertar_evidencia")
@login_requerido
def api_insertar_evidencia():
    """multipart/form-data: ticket_id + fotos (hasta 3 por ticket)."""
    from tickets import ErrorRegla, MAX_EVIDENCIAS, fotos_de_la_peticion, guardar_evidencias, obtener_ticket, validar_foto

    ticket = obtener_ticket(entero(request.form.get("ticket_id")), g.usuario)
    if not ticket:
        return error("el ticket no existe o no tienes acceso", 404)
    try:
        fotos = [validar_foto(a) for a in fotos_de_la_peticion()]
        if not fotos:
            return error("adjunta al menos una imagen en el campo 'fotos'")
        con = conexion()
        with con.cursor() as cur:
            guardar_evidencias(cur, ticket, fotos[:MAX_EVIDENCIAS], g.usuario["id"], [])
        con.commit()
    except ErrorRegla as e:
        return error(str(e))
    return ok({"ticket_id": ticket["id"], "fotos": len(fotos)}, "Evidencia insertada correctamente")


@api_postman_bp.get("/api_obtener_evidencias")
@login_requerido
def api_obtener_evidencias():
    from tickets import obtener_ticket

    ticket = obtener_ticket(entero(request.args.get("ticket_id")), g.usuario)
    if not ticket:
        return error("el ticket no existe o no tienes acceso", 404)
    filas = consultar("""SELECT id, ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type,
                                tamano_bytes, subido_por FROM ticket_evidencias WHERE ticket_id = %s ORDER BY orden""",
                      (ticket["id"],))
    return ok(filas, "Evidencias obtenidas correctamente")


# ------------------------------------------------------------------ historial
@api_postman_bp.post("/api_insertar_historial")
@login_requerido
def api_insertar_historial():
    """tipo = COMENTARIO (comentario) o CAMBIO_ESTADO (estado_nuevo + comentario) o ASIGNACION (tecnico_nuevo_id)."""
    from tickets import ErrorRegla, asignar_ticket, cambiar_estado, comentar, obtener_ticket

    d = cuerpo()
    ticket = obtener_ticket(entero(d.get("ticket_id")), g.usuario)
    if not ticket:
        return error("el ticket no existe o no tienes acceso", 404)
    tipo = (d.get("tipo") or "COMENTARIO").upper()
    try:
        if tipo == "CAMBIO_ESTADO":
            cambiar_estado(g.usuario, ticket, d.get("estado_nuevo", ""), d.get("comentario"))
        elif tipo == "ASIGNACION":
            asignar_ticket(g.usuario, ticket, entero(d.get("tecnico_nuevo_id")), d.get("comentario"))
        else:
            comentar(g.usuario, ticket, d.get("comentario"))
    except ErrorRegla as e:
        return error(str(e))
    return ok({"ticket_id": ticket["id"], "tipo": tipo}, "Historial registrado correctamente")


@api_postman_bp.get("/api_obtener_historial")
@login_requerido
def api_obtener_historial():
    from tickets import alcance

    condicion, params = alcance(g.usuario)
    sql = f"""SELECT h.* FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id WHERE {condicion}"""
    if request.args.get("ticket_id"):
        sql += " AND h.ticket_id = %s"
        params.append(entero(request.args.get("ticket_id")))
    return ok(serializar(consultar(sql + " ORDER BY h.created_at", params)), "Historial listado correctamente")


# ------------------------------------------------------------------ notificaciones
@api_postman_bp.post("/api_insertar_notificacion")
@roles_requeridos("Superusuario", "Administrador")
def api_insertar_notificacion():
    d = cuerpo()
    destino = consultar("SELECT empresa_id FROM users WHERE id = %s", (entero(d.get("usuario_id")),), uno=True)
    if not destino or (not es_super() and destino["empresa_id"] != g.usuario["empresa_id"]):
        return error("el usuario destino no existe en tu empresa", 404)
    nuevo = ejecutar(
        """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (d["usuario_id"], d["tipo"], d.get("referencia_ticket"), d["titulo"], d.get("mensaje"), ahora()),
    )
    return ok({"id": nuevo}, "Notificación insertada correctamente")


@api_postman_bp.get("/api_obtenernotificaciones")
@login_requerido
def api_obtenernotificaciones():
    filas = consultar(
        """SELECT id, usuario_id, tipo, referencia_ticket, titulo, mensaje, leido, leido_at, created_at
             FROM notificaciones WHERE usuario_id = %s ORDER BY created_at DESC""",
        (g.usuario["id"],),
    )
    return ok(serializar(filas), "Notificacion listado correctamente")
