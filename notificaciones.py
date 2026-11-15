from flask import Blueprint, g, jsonify, request

from auth import login_requerido
from db import conexion, consultar

notificaciones_bp = Blueprint("notificaciones", __name__)

LIMITE_LISTADO = 100
MAX_IDS_POR_ACCION = 200
TIPOS_TICKET = ("NUEVO_TICKET", "ASIGNACION", "CAMBIO_ESTADO", "COMENTARIO")
TIPOS_SISTEMA = ("SLA",)
TIPOS = TIPOS_TICKET + TIPOS_SISTEMA


def _usuario_id():
    return g.usuario_token["id"]


def _resumen():
    fila = consultar(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(leido = 0), 0) AS no_leidas,
                  COALESCE(SUM(tipo <> 'SLA'), 0) AS tickets,
                  COALESCE(SUM(tipo = 'SLA'), 0) AS sistema
             FROM notificaciones
            WHERE usuario_id = %s""",
        (_usuario_id(),),
        uno=True,
    )
    return {clave: int(valor) for clave, valor in fila.items()}


def _listado():
    filas = consultar(
        f"""SELECT id, tipo, referencia_ticket, titulo, mensaje, leido,
                   DATE_FORMAT(created_at, '%%d/%%m/%%Y %%H:%%i') AS fecha,
                   TIMESTAMPDIFF(MINUTE, created_at, NOW()) AS hace_minutos
              FROM notificaciones
             WHERE usuario_id = %s
             ORDER BY id DESC
             LIMIT {LIMITE_LISTADO}""",
        (_usuario_id(),),
    )
    for fila in filas:
        fila["leido"] = bool(fila["leido"])
        fila["categoria"] = "sistema" if fila["tipo"] in TIPOS_SISTEMA else "ticket"
    return filas


def _ids_de_la_peticion():
    datos = request.get_json(silent=True) or {}
    ids = datos.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS_POR_ACCION:
        return None
    if not all(type(i) is int and i > 0 for i in ids):
        return None
    return sorted(set(ids))


def _ejecutar(sql, params):
    con = conexion()
    with con.cursor() as cur:
        cur.execute(sql, params)
        afectadas = cur.rowcount
    con.commit()
    return afectadas


@notificaciones_bp.get("/api/notificaciones")
@login_requerido
def listar():
    return jsonify(ok=True, resumen=_resumen(), notificaciones=_listado())


@notificaciones_bp.route(
    "/api/notificaciones/<int:notif_id>/leer", methods=["POST", "PUT"]
)
@login_requerido
def marcar_leida(notif_id):
    existe = consultar(
        "SELECT id FROM notificaciones WHERE id = %s AND usuario_id = %s",
        (notif_id, _usuario_id()),
        uno=True,
    )
    if not existe:
        return jsonify(ok=False, error="La notificación no existe."), 404
    _ejecutar(
        "UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE id = %s AND leido = 0",
        (notif_id,),
    )
    return jsonify(ok=True)


@notificaciones_bp.route("/api/notificaciones/leer-todas", methods=["POST", "PUT"])
@login_requerido
def marcar_todas():
    marcadas = _ejecutar(
        "UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE usuario_id = %s AND leido = 0",
        (_usuario_id(),),
    )
    return jsonify(ok=True, marcadas=marcadas)


@notificaciones_bp.post("/api/notificaciones/leer-seleccion")
@login_requerido
def marcar_seleccion():
    ids = _ids_de_la_peticion()
    if ids is None:
        return jsonify(ok=False, error="Selecciona al menos una notificación."), 400
    marcadores = ", ".join(["%s"] * len(ids))
    marcadas = _ejecutar(
        f"""UPDATE notificaciones SET leido = 1, leido_at = NOW()
             WHERE usuario_id = %s AND leido = 0 AND id IN ({marcadores})""",
        (_usuario_id(), *ids),
    )
    return jsonify(ok=True, marcadas=marcadas)


@notificaciones_bp.post("/api/notificaciones/eliminar")
@login_requerido
def eliminar_seleccion():
    ids = _ids_de_la_peticion()
    if ids is None:
        return jsonify(ok=False, error="Selecciona al menos una notificación."), 400
    marcadores = ", ".join(["%s"] * len(ids))
    eliminadas = _ejecutar(
        f"DELETE FROM notificaciones WHERE usuario_id = %s AND id IN ({marcadores})",
        (_usuario_id(), *ids),
    )
    return jsonify(ok=True, eliminadas=eliminadas)
