from bd import obtenerconexion
from controlador_notificaciones import notificar
from utilidades import (CATEGORIAS, ESTADOS, ESTADOS_CIERRE, PRIORIDADES, ErrorNegocio, ahora, calcular_sla,
                        eliminar_archivos, guardar_fotos, iniciales, validar_fotos)

# Consulta base: datos del ticket + nombres del solicitante y del técnico + primera miniatura
SQL_TICKETS = """
    SELECT t.*,
           s.nombre AS solicitante_nombre, s.area AS solicitante_area,
           te.nombre AS tecnico_nombre,
           (SELECT f.miniatura FROM ticket_fotos f WHERE f.ticket_id = t.id ORDER BY f.id LIMIT 1) AS miniatura,
           (SELECT COUNT(*) FROM ticket_fotos f WHERE f.ticket_id = t.id) AS total_fotos
    FROM tickets t
    JOIN users s ON s.id = t.solicitante_id
    LEFT JOIN users te ON te.id = t.tecnico_id
"""


def _completar(ticket):
    """Agrega el código visible y el campo calculado de urgencia (SLA)."""
    ticket["codigo"] = "TK-" + str(ticket["id"]).zfill(4)
    ticket["sla"] = calcular_sla(ticket)
    ticket["tecnico_iniciales"] = iniciales(ticket["tecnico_nombre"]) if ticket["tecnico_nombre"] else None
    return ticket


def puede_ver(usuario, ticket):
    return usuario["rol"] != "Solicitante" or ticket["solicitante_id"] == usuario["id"]


def _condiciones_visibles(usuario, empresa):
    condiciones, parametros = [], []
    if usuario["rol"] == "Solicitante":
        condiciones.append("t.solicitante_id = %s")
        parametros.append(usuario["id"])
    if empresa:
        condiciones.append("t.empresa = %s")
        parametros.append(empresa)
    return condiciones, parametros


def _orden_urgencia(ticket):
    sla = ticket["sla"]
    # Abiertos primero (los que consumieron más plazo arriba); resueltos y cerrados al final
    if sla["cerrado"]:
        return (1, -ticket["cerrado_at"].timestamp())
    return (0, -sla["ratio"])


def listar(usuario, empresa="", filtros=None):
    """Tickets que el usuario puede ver, filtrados y ordenados por urgencia. Devuelve (lista, alertas)."""
    filtros = filtros or {}
    condiciones, parametros = _condiciones_visibles(usuario, empresa)
    sql = SQL_TICKETS + (" WHERE " + " AND ".join(condiciones) if condiciones else "")

    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            visibles = [_completar(t) for t in cursor.fetchall()]

    alertas = {
        "total": len(visibles),
        "vencidos": sum(1 for t in visibles if not t["sla"]["cerrado"] and t["sla"]["nivel"] == "rojo"),
        "por_vencer": sum(1 for t in visibles if not t["sla"]["cerrado"] and t["sla"]["nivel"] == "amarillo"),
    }

    q = (filtros.get("q") or "").strip().lower()
    tecnico = filtros.get("tecnico") or ""
    lista = []
    for t in visibles:
        if q and q not in (t["codigo"] + " " + t["asunto"]).lower():
            continue
        if filtros.get("estado") and t["estado"] != filtros["estado"]:
            continue
        if filtros.get("prioridad") and t["prioridad"] != filtros["prioridad"]:
            continue
        if tecnico == "sin" and t["tecnico_id"]:
            continue
        if tecnico not in ("", "sin") and str(t["tecnico_id"]) != str(tecnico):
            continue
        if filtros.get("urgentes") and (t["sla"]["cerrado"] or t["sla"]["nivel"] == "verde"):
            continue
        lista.append(t)

    lista.sort(key=_orden_urgencia)
    return lista, alertas


def obtener(usuario, ticket_id):
    """Ticket con fotos e historial. Lanza 404 si no existe o el usuario no puede verlo."""
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_TICKETS + " WHERE t.id = %s", (ticket_id,))
            ticket = cursor.fetchone()
            if ticket is None or not puede_ver(usuario, ticket):
                raise ErrorNegocio("No encontramos ese ticket.", 404)
            cursor.execute("SELECT * FROM ticket_fotos WHERE ticket_id = %s ORDER BY id", (ticket_id,))
            ticket["fotos"] = cursor.fetchall()
            cursor.execute("""
                SELECT h.*, u.nombre AS usuario_nombre, u.rol AS usuario_rol
                FROM ticket_historial h JOIN users u ON u.id = h.usuario_id
                WHERE h.ticket_id = %s ORDER BY h.created_at, h.id""", (ticket_id,))
            ticket["historial"] = cursor.fetchall()
    for h in ticket["historial"]:
        if h["tipo"] == "estado":
            h["titulo"] = "Estado cambiado: " + h["estado_anterior"] + " → " + h["estado_nuevo"]
        elif h["tipo"] == "asignado":
            h["titulo"] = h["texto"]
        elif h["tipo"] == "comentario":
            h["titulo"] = "Nuevo comentario"
        else:
            h["titulo"] = "Ticket creado"
        h["comentario"] = "" if h["tipo"] == "asignado" else h["texto"]
    return _completar(ticket)


def _validar_campos(datos, parcial=False):
    errores, limpio = {}, {}
    if not parcial or "asunto" in datos:
        limpio["asunto"] = (datos.get("asunto") or "").strip()
        if not 5 <= len(limpio["asunto"]) <= 120:
            errores["asunto"] = "Escribe un asunto de 5 a 120 caracteres."
    if not parcial or "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()
        if len(limpio["descripcion"]) < 10:
            errores["descripcion"] = "Describe el problema con al menos 10 caracteres."
    if not parcial or "categoria" in datos:
        limpio["categoria"] = datos.get("categoria") or ""
        if limpio["categoria"] not in CATEGORIAS:
            errores["categoria"] = "Elige una categoría."
    if not parcial or "prioridad" in datos:
        limpio["prioridad"] = datos.get("prioridad") or ""
        if limpio["prioridad"] not in PRIORIDADES:
            errores["prioridad"] = "Elige una prioridad."
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)
    return limpio


def _historial(cursor, ticket_id, usuario_id, tipo, texto, anterior=None, nuevo=None, fecha=None):
    sql = ("INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, texto, created_at) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s)")
    cursor.execute(sql, (ticket_id, usuario_id, tipo, anterior, nuevo, texto, fecha or ahora()))


def crear(solicitante, datos, archivos=()):
    campos = _validar_campos(datos)
    fotos = guardar_fotos(validar_fotos(archivos))
    momento = ahora()

    conexion = obtenerconexion()
    try:
        with conexion:
            with conexion.cursor() as cursor:
                sql = ("INSERT INTO tickets (asunto, descripcion, categoria, prioridad, estado, empresa, solicitante_id, "
                       "created_at, updated_at) VALUES (%s, %s, %s, %s, 'Abierto', %s, %s, %s, %s)")
                cursor.execute(sql, (campos["asunto"], campos["descripcion"], campos["categoria"], campos["prioridad"],
                                     solicitante["empresa"], solicitante["id"], momento, momento))
                ticket_id = cursor.lastrowid

                for f in fotos:
                    cursor.execute("INSERT INTO ticket_fotos (ticket_id, archivo, miniatura, nombre_original, mime, created_at) "
                                   "VALUES (%s, %s, %s, %s, %s, %s)",
                                   (ticket_id, f["archivo"], f["miniatura"], f["nombre_original"], f["mime"], momento))

                if len(fotos) == 1:
                    texto = "Se adjuntó 1 foto de evidencia."
                elif fotos:
                    texto = "Se adjuntaron " + str(len(fotos)) + " fotos de evidencia."
                else:
                    texto = "Ticket registrado."
                _historial(cursor, ticket_id, solicitante["id"], "creado", texto, fecha=momento)

                codigo = "TK-" + str(ticket_id).zfill(4)
                cursor.execute("SELECT id FROM users WHERE rol = 'Administrador' AND activo = 1")
                for admin in cursor.fetchall():
                    notificar(cursor, admin["id"], "nuevo", ticket_id, "Nuevo ticket " + codigo + " por asignar",
                              excepto=solicitante["id"])
            conexion.commit()
    except Exception:
        eliminar_archivos(fotos)  # si falla la BD, no quedan archivos sueltos
        raise
    return ticket_id


def actualizar(ticket, datos, actor):
    es_dueno = ticket["solicitante_id"] == actor["id"] and ticket["estado"] == "Abierto"
    if actor["rol"] != "Administrador" and not es_dueno:
        raise ErrorNegocio("Solo el administrador o el solicitante (con el ticket abierto) pueden editarlo.", 403)
    campos = _validar_campos(datos, parcial=True)
    if not campos:
        return
    sql = "UPDATE tickets SET " + ", ".join(k + " = %s" for k in campos) + ", updated_at = %s WHERE id = %s"
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, list(campos.values()) + [ahora(), ticket["id"]])
        conexion.commit()


def eliminar(ticket):
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM tickets WHERE id = %s", (ticket["id"],))  # fotos e historial se borran en cascada
        conexion.commit()
    eliminar_archivos(ticket["fotos"])


def asignar(ticket, tecnico_id, actor):
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT id, nombre FROM users WHERE id = %s AND rol = 'Técnico' AND activo = 1", (tecnico_id or 0,))
            tecnico = cursor.fetchone()
            if tecnico is None:
                raise ErrorNegocio("Elige un técnico activo.", 422, {"tecnico_id": "Elige un técnico activo."})
            if ticket["estado"] == "Cerrado":
                raise ErrorNegocio("No se puede asignar un ticket cerrado.", 409)
            if ticket["tecnico_id"] == tecnico["id"]:
                raise ErrorNegocio("El ticket ya está asignado a esa persona.", 409)

            cursor.execute("UPDATE tickets SET tecnico_id = %s, updated_at = %s WHERE id = %s",
                           (tecnico["id"], ahora(), ticket["id"]))
            _historial(cursor, ticket["id"], actor["id"], "asignado", "Ticket asignado a " + tecnico["nombre"])
            notificar(cursor, tecnico["id"], "asignacion", ticket["id"], "Se te asignó el ticket " + ticket["codigo"],
                      excepto=actor["id"])
            notificar(cursor, ticket["solicitante_id"], "asignacion", ticket["id"],
                      ticket["codigo"] + " fue asignado a " + tecnico["nombre"], excepto=actor["id"])
        conexion.commit()
    return tecnico


def cambiar_estado(ticket, nuevo, comentario, actor):
    if actor["rol"] == "Solicitante":
        raise ErrorNegocio("Solo el administrador o el técnico pueden cambiar el estado.", 403)
    if actor["rol"] == "Técnico" and ticket["tecnico_id"] != actor["id"]:
        raise ErrorNegocio("Solo el técnico asignado puede cambiar el estado de este ticket.", 403)

    comentario = (comentario or "").strip()
    errores = {}
    if nuevo not in ESTADOS:
        errores["estado"] = "Elige un estado válido."
    elif nuevo == ticket["estado"]:
        errores["estado"] = "Elige un estado distinto al actual (" + ticket["estado"] + ")."
    if len(comentario) < 5:
        errores["comentario"] = "Escribe un comentario para poder guardar el cambio."
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)

    momento = ahora()
    if nuevo in ESTADOS_CIERRE:
        cerrado_at = ticket["cerrado_at"] or momento
    else:
        cerrado_at = None

    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("UPDATE tickets SET estado = %s, cerrado_at = %s, updated_at = %s WHERE id = %s",
                           (nuevo, cerrado_at, momento, ticket["id"]))
            _historial(cursor, ticket["id"], actor["id"], "estado", comentario, ticket["estado"], nuevo, momento)
            mensaje = ticket["codigo"] + " cambió a " + nuevo
            notificar(cursor, ticket["solicitante_id"], "estado", ticket["id"], mensaje, excepto=actor["id"])
            notificar(cursor, ticket["tecnico_id"], "estado", ticket["id"], mensaje, excepto=actor["id"])
        conexion.commit()


def comentar(ticket, texto, actor):
    texto = (texto or "").strip()
    if len(texto) < 2:
        raise ErrorNegocio("Escribe el comentario antes de publicarlo.", 422, {"texto": "Escribe el comentario."})
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            _historial(cursor, ticket["id"], actor["id"], "comentario", texto)
            mensaje = "Nuevo comentario en " + ticket["codigo"]
            notificar(cursor, ticket["solicitante_id"], "comentario", ticket["id"], mensaje, excepto=actor["id"])
            notificar(cursor, ticket["tecnico_id"], "comentario", ticket["id"], mensaje, excepto=actor["id"])
        conexion.commit()


def foto_por_archivo(nombre):
    """Busca la foto (original o miniatura) para saber a qué ticket pertenece."""
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.*, t.solicitante_id FROM ticket_fotos f JOIN tickets t ON t.id = f.ticket_id
                WHERE f.archivo = %s OR f.miniatura = %s""", (nombre, nombre))
            return cursor.fetchone()


# ---------------------------------------------
# Conversión a JSON para la API
# ---------------------------------------------
def a_json(t, detalle=False):
    datos = {
        "id": t["id"], "codigo": t["codigo"], "asunto": t["asunto"], "categoria": t["categoria"],
        "prioridad": t["prioridad"], "estado": t["estado"], "empresa": t["empresa"],
        "solicitante": {"id": t["solicitante_id"], "nombre": t["solicitante_nombre"]},
        "tecnico": {"id": t["tecnico_id"], "nombre": t["tecnico_nombre"]} if t["tecnico_id"] else None,
        "created_at": t["created_at"].isoformat(),
        "cerrado_at": t["cerrado_at"].isoformat() if t["cerrado_at"] else None,
        "sla": {"nivel": t["sla"]["nivel"], "texto": t["sla"]["texto"], "horas_limite": t["sla"]["horas_limite"],
                "porcentaje_consumido": round(t["sla"]["ratio"] * 100)},
        "total_fotos": t["total_fotos"],
    }
    if detalle:
        datos["descripcion"] = t["descripcion"]
        datos["fotos"] = [{"id": f["id"], "nombre": f["nombre_original"], "url": "/uploads/" + f["archivo"],
                           "miniatura": "/uploads/" + f["miniatura"]} for f in t["fotos"]]
        datos["historial"] = [{"id": h["id"], "tipo": h["tipo"], "titulo": h["titulo"], "texto": h["texto"],
                               "usuario": {"id": h["usuario_id"], "nombre": h["usuario_nombre"], "rol": h["usuario_rol"]},
                               "created_at": h["created_at"].isoformat()} for h in t["historial"]]
    return datos
