import uuid

import pymysql

from flask import Blueprint, g, jsonify, request
from notificaciones import TIPOS as TIPOS_NOTIFICACION

from auth import (
    ROL_ADMIN,
    ROL_SUPER,
    empresa_actual,
    es_super,
    hashear,
    login_requerido,
    roles_requeridos,
    validar_clave_nueva,
)
from db import conexion, consultar
from utils import COLOR_RE, DOMINIO_RE, ROLES_EMPRESA, ahora, correo_valido, dominio_de, entero, fecha_iso

api_postman_bp = Blueprint("api_postman", __name__)


def ok(data=None, mensaje="OK", codigo=200):
    return jsonify(
        status=1, data=data if data is not None else {}, message=mensaje
    ), codigo


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
    if es_super():
        return entero(datos.get("empresa_id")) or empresa_actual()
    return g.usuario_token["empresa_id"]


@api_postman_bp.errorhandler(Exception)
def _cualquier_error(e):
    from werkzeug.exceptions import HTTPException

    if isinstance(e, HTTPException):
        return e
    if isinstance(e, KeyError):
        return error(f"falta el campo {e.args[0]}")
    return error(repr(e), 500)


@api_postman_bp.post("/api_insertar_empresa")
@roles_requeridos(ROL_SUPER)
def api_insertar_empresa():
    d = cuerpo()
    nuevo = ejecutar(
        """INSERT INTO empresas (codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema,
                                 color_primario, color_secundario, logo_url, activo, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            d["codigo"],
            d["nombre"],
            d.get("razon_social"),
            d.get("ruc"),
            d["prefijo_ticket"],
            d["titulo_sistema"],
            d["color_primario"],
            d["color_secundario"],
            d.get("logo_url"),
            d.get("activo", 1),
            ahora(),
        ),
    )
    return ok({"id": nuevo}, "Empresa insertada correctamente")


@api_postman_bp.get("/api_obtener_empresas")
@login_requerido
def api_obtener_empresas():
    sql = """SELECT id, codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema, color_primario,
                    color_secundario, logo_url, ultimo_ticket, activo, created_at FROM empresas"""
    filas = (
        consultar(sql)
        if es_super()
        else consultar(sql + " WHERE id = %s", (g.usuario_token["empresa_id"],))
    )
    return ok(serializar(filas), "Empresas obtenidas correctamente")


@api_postman_bp.post("/api_insertar_empresa_dominio")
@roles_requeridos(ROL_SUPER)
def api_insertar_empresa_dominio():
    d = cuerpo()
    nuevo = ejecutar(
        "INSERT INTO empresa_dominios (empresa_id, dominio) VALUES (%s, %s)",
        (d["empresa_id"], d["dominio"].strip().lower().lstrip("@")),
    )
    return ok({"id": nuevo}, "Dominio insertado correctamente")


@api_postman_bp.get("/api_obtener_empresa_dominios")
@login_requerido
def api_obtener_empresa_dominios():
    sql = "SELECT id, empresa_id, dominio FROM empresa_dominios"
    filas = (
        consultar(sql)
        if es_super()
        else consultar(sql + " WHERE empresa_id = %s", (g.usuario_token["empresa_id"],))
    )
    return ok(filas, "Dominios obtenidos correctamente")


@api_postman_bp.post("/api_insertar_area")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_insertar_area():
    d = cuerpo()
    empresa_id = empresa_de_peticion(d)
    if not empresa_id:
        return error("indica empresa_id")
    nuevo = ejecutar(
        "INSERT INTO areas (empresa_id, nombre, activo) VALUES (%s, %s, %s)",
        (empresa_id, d["nombre"], d.get("activo", 1)),
    )
    return ok(
        {"id": nuevo, "empresa_id": empresa_id, "nombre": d["nombre"]},
        "Area insertada correctamente",
    )


@api_postman_bp.get("/api_obtener_areas")
@login_requerido
def api_obtener_areas():
    sql = "SELECT id, empresa_id, nombre, activo FROM areas"
    filas = (
        consultar(sql + " ORDER BY id")
        if es_super()
        else consultar(
            sql + " WHERE empresa_id = %s ORDER BY id", (g.usuario_token["empresa_id"],)
        )
    )
    return ok(filas, "Areas obtenidas correctamente")


@api_postman_bp.post("/api_insertar_user")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_insertar_user():
    d = cuerpo()
    empresa_id = empresa_de_peticion(d)
    correo = (d.get("correo") or "").strip().lower()
    rol = d.get("rol", "Solicitante")
    if not empresa_id:
        return error("indica empresa_id")
    if rol not in ROLES_EMPRESA:
        return error("rol no válido (Administrador, Técnico o Solicitante)")
    if not correo_valido(correo) or not consultar(
        "SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
        (empresa_id, dominio_de(correo)),
        uno=True,
    ):
        return error("el correo debe usar el dominio de la empresa")
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
        (
            empresa_id,
            d.get("area_id"),
            d["nombre"],
            correo,
            password_hash,
            rol,
            d.get("activo", 1),
            momento,
            momento,
        ),
    )
    return ok(
        {
            "id": nuevo,
            "empresa_id": empresa_id,
            "nombre": d["nombre"],
            "correo": correo,
            "rol": rol,
        },
        "Usuario insertado correctamente",
    )


@api_postman_bp.get("/api_obtener_users")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_obtener_users():
    sql = "SELECT id, empresa_id, area_id, nombre, correo, rol, activo, ultimo_acceso, created_at, updated_at FROM users"
    filas = (
        consultar(sql + " ORDER BY id")
        if es_super()
        else consultar(
            sql + " WHERE empresa_id = %s ORDER BY id", (g.usuario_token["empresa_id"],)
        )
    )
    return ok(serializar(filas), "Usuarios obtenidos correctamente")


@api_postman_bp.post("/api_insertar_token_revocado")
@roles_requeridos(ROL_SUPER)
def api_insertar_token_revocado():
    d = cuerpo()
    jti = d.get("jti") or str(uuid.uuid4())
    nuevo = ejecutar(
        "INSERT INTO tokens_revocados (jti, usuario_id, expira_en, created_at) VALUES (%s, %s, %s, %s)",
        (jti, d.get("usuario_id"), d.get("expira_en"), ahora()),
    )
    return ok({"id": nuevo, "jti": jti}, "Token revocado insertado correctamente")


@api_postman_bp.get("/api_obtener_tokens_revocados")
@roles_requeridos(ROL_SUPER)
def api_obtener_tokens_revocados():
    return ok(
        serializar(
            consultar(
                "SELECT id, jti, usuario_id, expira_en, created_at FROM tokens_revocados"
            )
        ),
        "Tokens revocados obtenidos correctamente",
    )


@api_postman_bp.post("/api_insertar_categoria")
@roles_requeridos(ROL_SUPER)
def api_insertar_categoria():
    d = cuerpo()
    nuevo = ejecutar(
        "INSERT INTO categorias (nombre, descripcion, activo) VALUES (%s, %s, %s)",
        (d["nombre"], d.get("descripcion"), d.get("activo", 1)),
    )
    return ok({"id": nuevo}, "Categoría insertada correctamente")


@api_postman_bp.get("/api_obtener_categorias")
@login_requerido
def api_obtener_categorias():
    return ok(
        consultar("SELECT id, nombre, descripcion, activo FROM categorias"),
        "Categorías obtenidas correctamente",
    )


@api_postman_bp.post("/api_insertar_prioridad")
@roles_requeridos(ROL_SUPER)
def api_insertar_prioridad():
    d = cuerpo()
    ejecutar(
        "INSERT INTO prioridades (id, nombre, sla_horas, nivel) VALUES (%s, %s, %s, %s)",
        (d["id"], d["nombre"], d["sla_horas"], d["nivel"]),
    )
    return ok({"id": d["id"]}, "Prioridad insertada correctamente")


@api_postman_bp.get("/api_obtener_prioridades")
@login_requerido
def api_obtener_prioridades():
    return ok(
        consultar(
            "SELECT id, nombre, sla_horas, nivel FROM prioridades ORDER BY nivel DESC"
        ),
        "Prioridades obtenidas correctamente",
    )


def _con_usuario_de_tickets(vista):
    from tickets import login_requerido as login_tickets

    return login_tickets(vista)


@api_postman_bp.post("/api_insertar_ticket")
@login_requerido
def api_insertar_ticket():

    @_con_usuario_de_tickets
    def _crear():
        from tickets import ErrorRegla, Ticket

        if g.usuario["es_super"]:
            return error("el superusuario no registra tickets", 403)
        datos, errores = Ticket.validar(cuerpo(), g.usuario)
        if errores:
            return error("; ".join(errores.values()))
        con = conexion()
        try:
            with con.cursor() as cur:
                ticket_id = Ticket.crear(
                    cur, datos, g.usuario["id"], g.usuario["empresa_id"]
                )
            con.commit()
        except ErrorRegla as e:
            con.rollback()
            return error(str(e))
        t = Ticket.obtener(ticket_id, g.usuario["empresa_id"])
        return ok(
            {"id": ticket_id, "codigo": t["codigo"]}, "Ticket insertado correctamente"
        )

    return _crear()


@api_postman_bp.get("/api_obtener_tickets")
@login_requerido
def api_obtener_tickets():
    @_con_usuario_de_tickets
    def _listar():
        from tickets import Ticket, _ticket_resumen

        filas = Ticket.listar(g.usuario, {"limite": 500})
        return ok(
            [_ticket_resumen(t) for t in filas], "Tickets obtenidos correctamente"
        )

    return _listar()


@api_postman_bp.post("/api_insertar_evidencia")
@login_requerido
def api_insertar_evidencia():

    @_con_usuario_de_tickets
    def _subir():
        from tickets import agregar_evidencias

        ticket_id = entero(request.form.get("ticket_id"))
        if not ticket_id:
            return error("envía ticket_id en form-data")
        respuesta = agregar_evidencias.__wrapped__(ticket_id)
        datos, codigo = (
            respuesta if isinstance(respuesta, tuple) else (respuesta, 200)
        )[:2]
        cuerpo_json = datos.get_json()
        if codigo >= 400:
            return error(cuerpo_json.get("error", "no se pudo subir"), codigo)
        return ok(
            {"ticket_id": ticket_id},
            cuerpo_json.get("mensaje", "Evidencia insertada correctamente"),
        )

    return _subir()


@api_postman_bp.get("/api_obtener_evidencias")
@login_requerido
def api_obtener_evidencias():
    @_con_usuario_de_tickets
    def _ver():
        from tickets import Ticket, puede_ver

        ticket = Ticket.obtener(
            entero(request.args.get("ticket_id")), g.usuario["empresa_id"]
        )
        if not ticket or not puede_ver(g.usuario, ticket):
            return error("el ticket no existe o no tienes acceso", 404)
        filas = consultar(
            """SELECT id, ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type,
                                    tamano_bytes, subido_por FROM ticket_evidencias WHERE ticket_id = %s ORDER BY orden""",
            (ticket["id"],),
        )
        return ok(filas, "Evidencias obtenidas correctamente")

    return _ver()


@api_postman_bp.post("/api_insertar_historial")
@login_requerido
def api_insertar_historial():

    @_con_usuario_de_tickets
    def _registrar():
        from tickets import ErrorRegla, Ticket, comentar_ticket, puede_ver

        d = cuerpo()
        ticket_id = entero(d.get("ticket_id"))
        ticket = Ticket.obtener(ticket_id, g.usuario["empresa_id"])
        if not ticket or not puede_ver(g.usuario, ticket):
            return error("el ticket no existe o no tienes acceso", 404)
        tipo = (d.get("tipo") or "COMENTARIO").upper()
        if tipo == "COMENTARIO":
            respuesta = comentar_ticket.__wrapped__(ticket_id)
            datos, codigo = (
                respuesta if isinstance(respuesta, tuple) else (respuesta, 200)
            )[:2]
            if codigo >= 400:
                return error(
                    datos.get_json().get("error", "no se pudo comentar"), codigo
                )
            return ok(
                {"ticket_id": ticket_id, "tipo": tipo},
                "Comentario registrado correctamente",
            )
        cambios = {"comentario": d.get("comentario", "")}
        if tipo == "CAMBIO_ESTADO":
            cambios["estado"] = d.get("estado_nuevo", "")
        elif tipo == "ASIGNACION":
            tecnico = consultar(
                "SELECT nombre FROM users WHERE id = %s AND empresa_id = %s",
                (entero(d.get("tecnico_nuevo_id")), g.usuario["empresa_id"]),
                uno=True,
            )
            if not tecnico:
                return error("el técnico no existe en tu empresa", 404)
            cambios["tecnico"] = tecnico["nombre"]
        else:
            return error("tipo no válido (COMENTARIO, CAMBIO_ESTADO o ASIGNACION)")
        con = conexion()
        try:
            with con.cursor() as cur:
                resultado = Ticket.actualizar_gestion(
                    cur, ticket_id, cambios, g.usuario
                )
            con.commit()
        except ErrorRegla as e:
            con.rollback()
            return error(str(e))
        if resultado and resultado.get(
            "tecnico_avisar"
        ):
            from avisos_whatsapp import avisar_asignacion

            avisar_asignacion(
                ticket_id,
                resultado["tecnico_avisar"],
                resultado["reasignacion"],
                g.usuario["empresa_id"],
                g.usuario["id"],
            )
        return ok(
            {"ticket_id": ticket_id, "tipo": tipo}, "Historial registrado correctamente"
        )

    return _registrar()


@api_postman_bp.get("/api_obtener_historial")
@login_requerido
def api_obtener_historial():
    @_con_usuario_de_tickets
    def _ver():
        params = [g.usuario["empresa_id"]]
        sql = "SELECT h.* FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id WHERE t.empresa_id = %s"
        if g.usuario["rol"] == "Solicitante":
            sql += " AND t.solicitante_id = %s"
            params.append(g.usuario["id"])
        if request.args.get("ticket_id"):
            sql += " AND h.ticket_id = %s"
            params.append(entero(request.args.get("ticket_id")))
        return ok(
            serializar(consultar(sql + " ORDER BY h.created_at", params)),
            "Historial listado correctamente",
        )

    return _ver()


@api_postman_bp.post("/api_insertar_notificacion")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_insertar_notificacion():
    d = cuerpo()
    titulo = (d.get("titulo") or "").strip()
    if d.get("tipo") not in TIPOS_NOTIFICACION:
        return error(f"tipo debe ser uno de: {', '.join(TIPOS_NOTIFICACION)}")
    if not titulo:
        return error("titulo es obligatorio")
    destino = consultar(
        "SELECT empresa_id FROM users WHERE id = %s",
        (entero(d.get("usuario_id")),),
        uno=True,
    )
    if not destino or (
        not es_super() and destino["empresa_id"] != g.usuario_token["empresa_id"]
    ):
        return error("el usuario destino no existe en tu empresa", 404)
    ticket_id = entero(d.get("referencia_ticket"))
    if ticket_id and not consultar(
        "SELECT id FROM tickets WHERE id = %s AND empresa_id = %s",
        (ticket_id, destino["empresa_id"]),
        uno=True,
    ):
        return error("el ticket de referencia no existe en la empresa del usuario", 404)
    nuevo = ejecutar(
        """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            d["usuario_id"],
            d["tipo"],
            ticket_id,
            titulo[:150],
            (d.get("mensaje") or "")[:255] or None,
            ahora(),
        ),
    )
    return ok({"id": nuevo}, "Notificación insertada correctamente")


@api_postman_bp.get("/api_obtenernotificaciones")
@login_requerido
def api_obtenernotificaciones():
    filas = consultar(
        """SELECT id, usuario_id, tipo, referencia_ticket, titulo, mensaje, leido, leido_at, created_at
             FROM notificaciones WHERE usuario_id = %s ORDER BY created_at DESC""",
        (g.usuario_token["id"],),
    )
    return ok(serializar(filas), "Notificacion listado correctamente")


def actualizar(tabla, registro_id, cambios):
    if not cambios:
        return False
    columnas = ", ".join(f"{col} = %s" for col in cambios)
    ejecutar(f"UPDATE {tabla} SET {columnas} WHERE id = %s", (*cambios.values(), registro_id))
    return True


def campos_enviados(datos, permitidos):
    return {campo: datos[campo] for campo in permitidos if campo in datos}


def error_integridad(e):
    codigo = e.args[0] if e.args else None
    if codigo == 1062:
        return error("ya existe un registro con ese valor (correo, nombre, RUC, prefijo o dominio repetido)", 409)
    if codigo == 1451:
        return error("no se puede eliminar: tiene registros relacionados (tickets, usuarios, etc.). "
                     "Desactívalo con activo = 0", 409)
    return error(str(e), 400)


def empresa_permitida(empresa_id):
    return es_super() or empresa_id == g.usuario_token["empresa_id"]


@api_postman_bp.put("/api_modificar_empresa/<int:empresa_id>")
@roles_requeridos(ROL_SUPER)
def api_modificar_empresa(empresa_id):
    if not consultar("SELECT 1 FROM empresas WHERE id = %s", (empresa_id,), uno=True):
        return error("la empresa no existe", 404)
    cambios = campos_enviados(cuerpo(), (
        "nombre", "razon_social", "ruc", "prefijo_ticket", "titulo_sistema",
        "color_primario", "color_secundario", "logo_url", "activo",
    ))
    if "ruc" in cambios and cambios["ruc"] and (not str(cambios["ruc"]).isdigit() or len(str(cambios["ruc"])) != 11):
        return error("el RUC tiene 11 dígitos")
    if "prefijo_ticket" in cambios:
        cambios["prefijo_ticket"] = str(cambios["prefijo_ticket"]).strip().upper()
        if not cambios["prefijo_ticket"].isalpha() or not 2 <= len(cambios["prefijo_ticket"]) <= 5:
            return error("el prefijo debe tener de 2 a 5 letras")
    for color in ("color_primario", "color_secundario"):
        if color in cambios and not COLOR_RE.match(str(cambios[color])):
            return error(f"{color} debe tener el formato #RRGGBB")
    try:
        if not actualizar("empresas", empresa_id, cambios):
            return error("no enviaste ningún campo para modificar")
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    fila = consultar("SELECT * FROM empresas WHERE id = %s", (empresa_id,), uno=True)
    return ok(serializar([fila])[0], "Empresa modificada correctamente")


@api_postman_bp.delete("/api_eliminar_empresa/<int:empresa_id>")
@roles_requeridos(ROL_SUPER)
def api_eliminar_empresa(empresa_id):
    empresa = consultar("SELECT id, nombre FROM empresas WHERE id = %s", (empresa_id,), uno=True)
    if not empresa:
        return error("la empresa no existe", 404)
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute("DELETE FROM empresa_dominios WHERE empresa_id = %s", (empresa_id,))
            cur.execute("DELETE FROM areas WHERE empresa_id = %s", (empresa_id,))
            cur.execute("DELETE FROM empresas WHERE id = %s", (empresa_id,))
        con.commit()
    except pymysql.err.IntegrityError as e:
        con.rollback()
        return error_integridad(e)
    return ok({"id": empresa_id}, f"Empresa {empresa['nombre']} eliminada correctamente")


@api_postman_bp.put("/api_modificar_empresa_dominio/<int:dominio_id>")
@roles_requeridos(ROL_SUPER)
def api_modificar_empresa_dominio(dominio_id):
    if not consultar("SELECT 1 FROM empresa_dominios WHERE id = %s", (dominio_id,), uno=True):
        return error("el dominio no existe", 404)
    dominio = (cuerpo().get("dominio") or "").strip().lower().lstrip("@")
    if not DOMINIO_RE.match(dominio):
        return error("escribe el dominio sin @, por ejemplo epsel.com.pe")
    try:
        actualizar("empresa_dominios", dominio_id, {"dominio": dominio})
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    return ok({"id": dominio_id, "dominio": dominio}, "Dominio modificado correctamente")


@api_postman_bp.delete("/api_eliminar_empresa_dominio/<int:dominio_id>")
@roles_requeridos(ROL_SUPER)
def api_eliminar_empresa_dominio(dominio_id):
    fila = consultar("SELECT empresa_id FROM empresa_dominios WHERE id = %s", (dominio_id,), uno=True)
    if not fila:
        return error("el dominio no existe", 404)
    total = consultar("SELECT COUNT(*) AS n FROM empresa_dominios WHERE empresa_id = %s",
                      (fila["empresa_id"],), uno=True)["n"]
    if total <= 1:
        return error("es el único dominio de la empresa: sin él nadie podría iniciar sesión", 409)
    ejecutar("DELETE FROM empresa_dominios WHERE id = %s", (dominio_id,))
    return ok({"id": dominio_id}, "Dominio eliminado correctamente")


@api_postman_bp.put("/api_modificar_area/<int:area_id>")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_modificar_area(area_id):
    area = consultar("SELECT empresa_id FROM areas WHERE id = %s", (area_id,), uno=True)
    if not area or not empresa_permitida(area["empresa_id"]):
        return error("el área no existe en tu empresa", 404)
    cambios = campos_enviados(cuerpo(), ("nombre", "activo"))
    try:
        if not actualizar("areas", area_id, cambios):
            return error("no enviaste ningún campo para modificar")
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    fila = consultar("SELECT id, empresa_id, nombre, activo FROM areas WHERE id = %s", (area_id,), uno=True)
    return ok(fila, "Area modificada correctamente")


@api_postman_bp.delete("/api_eliminar_area/<int:area_id>")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_eliminar_area(area_id):
    area = consultar("SELECT empresa_id FROM areas WHERE id = %s", (area_id,), uno=True)
    if not area or not empresa_permitida(area["empresa_id"]):
        return error("el área no existe en tu empresa", 404)
    try:
        ejecutar("DELETE FROM areas WHERE id = %s", (area_id,))
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    return ok({"id": area_id}, "Area eliminada correctamente")


def _usuario_editable(usuario_id):
    fila = consultar("SELECT id, empresa_id, rol, activo FROM users WHERE id = %s", (usuario_id,), uno=True)
    if not fila or fila["rol"] == ROL_SUPER or not empresa_permitida(fila["empresa_id"]):
        return None
    return fila


def _queda_sin_admin(usuario, rol_nuevo, activo_nuevo):
    if usuario["rol"] != ROL_ADMIN or not usuario["activo"]:
        return False
    if rol_nuevo == ROL_ADMIN and activo_nuevo:
        return False
    otros = consultar(
        "SELECT COUNT(*) AS n FROM users WHERE empresa_id = %s AND rol = %s AND activo = 1 AND id <> %s",
        (usuario["empresa_id"], ROL_ADMIN, usuario["id"]), uno=True)
    return otros["n"] == 0


@api_postman_bp.put("/api_modificar_user/<int:usuario_id>")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_modificar_user(usuario_id):
    usuario = _usuario_editable(usuario_id)
    if not usuario:
        return error("el usuario no existe en tu empresa", 404)
    d = cuerpo()
    cambios = campos_enviados(d, ("nombre", "correo", "rol", "area_id", "activo"))

    if "correo" in cambios:
        cambios["correo"] = str(cambios["correo"]).strip().lower()
        if not correo_valido(cambios["correo"]) or not consultar(
            "SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
            (usuario["empresa_id"], dominio_de(cambios["correo"])), uno=True,
        ):
            return error("el correo debe usar el dominio de la empresa")
    if "rol" in cambios:
        if cambios["rol"] not in ROLES_EMPRESA:
            return error("rol no válido (Administrador, Técnico o Solicitante)")
        if usuario_id == g.usuario_token["id"]:
            return error("no puedes cambiar tu propio rol", 403)
    if "area_id" in cambios and cambios["area_id"] and not consultar(
        "SELECT 1 FROM areas WHERE id = %s AND empresa_id = %s",
        (cambios["area_id"], usuario["empresa_id"]), uno=True,
    ):
        return error("el área no pertenece a la empresa del usuario")
    if "activo" in cambios:
        cambios["activo"] = 1 if str(cambios["activo"]).lower() in ("1", "true") else 0
        if usuario_id == g.usuario_token["id"] and not cambios["activo"]:
            return error("no puedes desactivar tu propia cuenta", 403)
    if _queda_sin_admin(usuario, cambios.get("rol", usuario["rol"]), cambios.get("activo", usuario["activo"])):
        return error("la empresa debe conservar al menos un administrador activo", 409)
    if d.get("password"):
        error_clave = validar_clave_nueva(d["password"])
        if error_clave:
            return error(error_clave)
        cambios["password_hash"] = hashear(d["password"])

    if not cambios:
        return error("no enviaste ningún campo para modificar")
    cambios["updated_at"] = ahora()
    try:
        actualizar("users", usuario_id, cambios)
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    fila = consultar("""SELECT id, empresa_id, area_id, nombre, correo, rol, activo, ultimo_acceso,
                               created_at, updated_at FROM users WHERE id = %s""", (usuario_id,), uno=True)
    return ok(serializar([fila])[0], "Usuario modificado correctamente")


@api_postman_bp.delete("/api_eliminar_user/<int:usuario_id>")
@roles_requeridos(ROL_SUPER, ROL_ADMIN)
def api_eliminar_user(usuario_id):
    usuario = _usuario_editable(usuario_id)
    if not usuario:
        return error("el usuario no existe en tu empresa", 404)
    if usuario_id == g.usuario_token["id"]:
        return error("no puedes eliminar tu propia cuenta", 403)
    if _queda_sin_admin(usuario, None, 0):
        return error("no puedes eliminar al único administrador activo de la empresa", 409)
    try:
        ejecutar("DELETE FROM users WHERE id = %s", (usuario_id,))
    except pymysql.err.IntegrityError as e:
        return error_integridad(e)
    return ok({"id": usuario_id}, "Usuario eliminado correctamente")


@api_postman_bp.delete("/api_eliminar_token_revocado/<int:token_id>")
@roles_requeridos(ROL_SUPER)
def api_eliminar_token_revocado(token_id):
    if not consultar("SELECT 1 FROM tokens_revocados WHERE id = %s", (token_id,), uno=True):
        return error("el token no existe", 404)
    ejecutar("DELETE FROM tokens_revocados WHERE id = %s", (token_id,))
    return ok({"id": token_id}, "Token revocado eliminado correctamente")