from bd import obtenerconexion
from utilidades import ahora


def notificar(cursor, usuario_id, tipo, ticket_id, mensaje, excepto=None):
    """Crea una notificación usando el cursor de una operación en curso (se confirma con su commit)."""
    if usuario_id and usuario_id != excepto:
        sql = ("INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, mensaje, leido, created_at) "
               "VALUES (%s, %s, %s, %s, 0, %s)")
        cursor.execute(sql, (usuario_id, tipo, ticket_id, mensaje, ahora()))


def contar_no_leidas(usuario_id):
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM notificaciones WHERE usuario_id = %s AND leido = 0", (usuario_id,))
            return cursor.fetchone()["total"]


def listar(usuario_id, solo_no_leidas=False):
    sql = ("SELECT n.id, n.tipo, n.referencia_ticket, n.mensaje, n.leido, n.created_at, t.asunto "
           "FROM notificaciones n JOIN tickets t ON t.id = n.referencia_ticket "
           "WHERE n.usuario_id = %s")
    if solo_no_leidas:
        sql += " AND n.leido = 0"
    sql += " ORDER BY n.created_at DESC, n.id DESC LIMIT 100"
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, (usuario_id,))
            notificaciones = cursor.fetchall()
    for n in notificaciones:
        n["leido"] = bool(n["leido"])
    return notificaciones


def obtener(usuario_id, notificacion_id):
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT * FROM notificaciones WHERE id = %s AND usuario_id = %s", (notificacion_id, usuario_id))
            return cursor.fetchone()


def marcar_leidas(usuario_id, ids=None):
    """Marca como leídas las notificaciones indicadas, o todas si ids es None."""
    sql = "UPDATE notificaciones SET leido = 1 WHERE usuario_id = %s AND leido = 0"
    parametros = [usuario_id]
    if ids is not None:
        if not ids:
            return 0
        sql += " AND id IN (" + ", ".join(["%s"] * len(ids)) + ")"
        parametros += list(ids)
    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            total = cursor.execute(sql, parametros)
        conexion.commit()
    return total


def a_json(n):
    return {"id": n["id"], "tipo": n["tipo"], "mensaje": n["mensaje"], "leido": bool(n["leido"]),
            "referencia_ticket": n["referencia_ticket"], "created_at": n["created_at"].isoformat()}
