"""
MÓDULO 5 — Notificaciones internas.

* Python genera las notificaciones (antes lo hacía un trigger) al crear,
  asignar, cambiar de estado o comentar un ticket: función notificar().
* La campana del menú consulta el contador por AJAX/fetch cada 30 s.
* Se marcan como leídas una por una o todas a la vez (UPDATE).
"""
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from auth import login_requerido
from db import conexion, consultar
from utils import ahora, hace

notificaciones_bp = Blueprint("notificaciones", __name__)

ICONOS = {
    "NUEVO_TICKET": "ticket",
    "ASIGNACION": "asignar",
    "CAMBIO_ESTADO": "estado",
    "COMENTARIO": "comentario",
    "SLA": "alerta",
}


def notificar(cur, destinatarios, tipo, ticket_id, titulo, mensaje="", excluir=None):
    """Inserta una notificación para cada destinatario (sin repetir y sin avisarse a sí mismo).
    Se usa dentro de la misma transacción que el cambio del ticket."""
    momento = ahora()
    vistos = set()
    for usuario_id in destinatarios:
        if not usuario_id or usuario_id == excluir or usuario_id in vistos:
            continue
        vistos.add(usuario_id)
        cur.execute(
            """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (usuario_id, tipo, ticket_id, titulo[:150], (mensaje or "")[:255], momento),
        )


def administradores_de(cur, empresa_id):
    cur.execute(
        "SELECT id FROM users WHERE empresa_id = %s AND rol = 'Administrador' AND activo = 1",
        (empresa_id,),
    )
    return [f["id"] for f in cur.fetchall()]


def contar_no_leidas(usuario_id):
    fila = consultar(
        "SELECT COUNT(*) AS total FROM notificaciones WHERE usuario_id = %s AND leido = 0",
        (usuario_id,), uno=True,
    )
    return fila["total"] if fila else 0


def _listar(usuario_id, solo_no_leidas=False, limite=50):
    filtro = "AND n.leido = 0" if solo_no_leidas else ""
    filas = consultar(
        f"""SELECT n.id, n.tipo, n.referencia_ticket, n.titulo, n.mensaje, n.leido, n.created_at
              FROM notificaciones n
             WHERE n.usuario_id = %s {filtro}
             ORDER BY n.created_at DESC, n.id DESC
             LIMIT %s""",
        (usuario_id, limite),
    )
    momento = ahora()
    for f in filas:
        f["icono"] = ICONOS.get(f["tipo"], "ticket")
        f["hace"] = hace(f["created_at"], momento)
    return filas


# ---------------------------------------------------------------- páginas
@notificaciones_bp.get("/notificaciones")
@login_requerido
def pagina():
    filtro = request.args.get("ver", "todas")
    return render_template(
        "notificaciones.html",
        notificaciones=_listar(g.usuario["id"], filtro == "no_leidas"),
        filtro=filtro,
    )


@notificaciones_bp.get("/notificaciones/<int:notif_id>/abrir")
@login_requerido
def abrir(notif_id):
    """Marca como leída y lleva al ticket."""
    fila = consultar(
        "SELECT referencia_ticket FROM notificaciones WHERE id = %s AND usuario_id = %s",
        (notif_id, g.usuario["id"]), uno=True,
    )
    _marcar(notif_id)
    if fila and fila["referencia_ticket"]:
        return redirect(url_for("tickets.detalle", ticket_id=fila["referencia_ticket"]))
    return redirect(url_for("notificaciones.pagina"))


def _marcar(notif_id=None):
    con = conexion()
    with con.cursor() as cur:
        if notif_id:   # individual
            cur.execute(
                "UPDATE notificaciones SET leido = 1, leido_at = %s WHERE id = %s AND usuario_id = %s AND leido = 0",
                (ahora(), notif_id, g.usuario["id"]),
            )
        else:          # masivo
            cur.execute(
                "UPDATE notificaciones SET leido = 1, leido_at = %s WHERE usuario_id = %s AND leido = 0",
                (ahora(), g.usuario["id"]),
            )
        cambiadas = cur.rowcount
    con.commit()
    return cambiadas


@notificaciones_bp.post("/notificaciones/<int:notif_id>/leer")
@login_requerido
def leer(notif_id):
    _marcar(notif_id)
    return redirect(request.referrer or url_for("notificaciones.pagina"))


@notificaciones_bp.post("/notificaciones/leer-todas")
@login_requerido
def leer_todas():
    total = _marcar()
    flash(f"{total} notificación(es) marcadas como leídas." if total else "No tenías notificaciones sin leer.", "ok")
    return redirect(request.referrer or url_for("notificaciones.pagina"))


# ---------------------------------------------------------------- API (fetch)
@notificaciones_bp.get("/api/notificaciones/contador")
@login_requerido
def api_contador():
    return jsonify(ok=True, no_leidas=contar_no_leidas(g.usuario["id"]))


@notificaciones_bp.get("/api/notificaciones")
@login_requerido
def api_listar():
    filas = _listar(g.usuario["id"], request.args.get("no_leidas") == "1", 20)
    for f in filas:
        f["created_at"] = f["created_at"].isoformat(timespec="seconds")
        f["url"] = url_for("notificaciones.abrir", notif_id=f["id"])
    return jsonify(ok=True, no_leidas=contar_no_leidas(g.usuario["id"]), notificaciones=filas)


@notificaciones_bp.route("/api/notificaciones/<int:notif_id>/leer", methods=["POST", "PUT"])
@login_requerido
def api_leer(notif_id):
    _marcar(notif_id)
    return jsonify(ok=True, no_leidas=contar_no_leidas(g.usuario["id"]))


@notificaciones_bp.route("/api/notificaciones/leer-todas", methods=["POST", "PUT"])
@login_requerido
def api_leer_todas():
    total = _marcar()
    return jsonify(ok=True, marcadas=total, no_leidas=0)
