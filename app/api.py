"""API REST (módulo 6). Todas las rutas, salvo el login, piden el header:
    Authorization: Bearer <token>
"""
import math

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import func

from . import servicios as srv
from .auth import emitir_token, protegido, revocar_token_actual
from .errores import ErrorNegocio
from .extensions import db
from .models import Notificacion, Ticket, Usuario, iso
from .reportes import descripcion_filtros, generar_excel, generar_pdf
from .sla import ahora

api_bp = Blueprint("api", __name__)


@api_bp.errorhandler(ErrorNegocio)
def error_negocio(e):
    db.session.rollback()
    cuerpo = {"error": e.mensaje}
    if e.campos:
        cuerpo["campos"] = e.campos
    return jsonify(cuerpo), e.status


def _json():
    return request.get_json(silent=True) or {}


def _empresa():
    return request.args.get("empresa", "")


# ---------------------------------------------------------------- autenticación
@api_bp.post("/auth/login")
def login():
    datos = _json()
    correo = (datos.get("correo") or "").strip().lower()
    usuario = Usuario.query.filter(func.lower(Usuario.correo) == correo).first()
    if usuario is None or not usuario.check_password(datos.get("password") or ""):
        return jsonify(error="Correo o contraseña incorrectos."), 401
    if not usuario.activo:
        return jsonify(error="La cuenta está desactivada."), 403
    token, _ = emitir_token(usuario)
    return jsonify(access_token=token, token_type="Bearer",
                   expires_in=int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
                   usuario=usuario.to_dict())


@api_bp.post("/auth/logout")
@protegido()
def logout():
    revocar_token_actual()
    return jsonify(mensaje="Sesión cerrada. El token ya no es válido.")


@api_bp.get("/auth/yo")
@protegido()
def yo():
    return jsonify(g.usuario.to_dict())


# ---------------------------------------------------------------- usuarios (solo administrador)
@api_bp.get("/usuarios")
@protegido("Administrador")
def usuarios_listar():
    consulta = Usuario.query
    if request.args.get("rol"):
        consulta = consulta.filter_by(rol=request.args["rol"])
    if request.args.get("activo") in ("true", "false"):
        consulta = consulta.filter_by(activo=request.args["activo"] == "true")
    if _empresa():
        consulta = consulta.filter_by(empresa=_empresa())
    return jsonify([u.to_dict() for u in consulta.order_by(Usuario.nombre)])


@api_bp.post("/usuarios")
@protegido("Administrador")
def usuarios_crear():
    return jsonify(srv.crear_usuario(_json()).to_dict()), 201


@api_bp.get("/usuarios/<int:usuario_id>")
@protegido("Administrador")
def usuarios_obtener(usuario_id):
    return jsonify(db.get_or_404(Usuario, usuario_id).to_dict())


@api_bp.put("/usuarios/<int:usuario_id>")
@protegido("Administrador")
def usuarios_actualizar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    datos = {**usuario.to_dict(), **_json()}
    return jsonify(srv.actualizar_usuario(usuario, datos, g.usuario).to_dict())


@api_bp.delete("/usuarios/<int:usuario_id>")
@protegido("Administrador")
def usuarios_desactivar(usuario_id):
    """No borra el registro (sus tickets lo referencian): lo desactiva."""
    usuario = srv.cambiar_activo(db.get_or_404(Usuario, usuario_id), False, g.usuario)
    return jsonify(usuario.to_dict())


# ---------------------------------------------------------------- tickets
@api_bp.get("/tickets")
@protegido()
def tickets_listar():
    filtros = {k: request.args.get(k, "") for k in ("q", "estado", "prioridad", "tecnico", "urgentes")}
    lista, alertas = srv.listar_tickets(g.usuario, _empresa(), filtros)
    por_pagina = min(max(request.args.get("por_pagina", 20, type=int), 1), 100)
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    inicio = (pagina - 1) * por_pagina
    return jsonify(datos=[t.to_dict() for t in lista[inicio:inicio + por_pagina]],
                   pagina=pagina, por_pagina=por_pagina, total=len(lista),
                   paginas=max(1, math.ceil(len(lista) / por_pagina)), alertas=alertas)


@api_bp.post("/tickets")
@protegido()
def tickets_crear():
    """Acepta JSON o multipart/form-data (campo 'fotos', hasta 3 imágenes)."""
    if request.content_type and request.content_type.startswith("multipart/"):
        datos, archivos = request.form.to_dict(), request.files.getlist("fotos")
    else:
        datos, archivos = _json(), []
    ticket = srv.crear_ticket(g.usuario, datos, archivos)
    return jsonify(ticket.to_dict(detalle=True)), 201


@api_bp.get("/tickets/<int:ticket_id>")
@protegido()
def tickets_obtener(ticket_id):
    return jsonify(srv.obtener_ticket(g.usuario, ticket_id).to_dict(detalle=True))


@api_bp.put("/tickets/<int:ticket_id>")
@protegido()
def tickets_actualizar(ticket_id):
    ticket = srv.actualizar_ticket(srv.obtener_ticket(g.usuario, ticket_id), _json(), g.usuario)
    return jsonify(ticket.to_dict(detalle=True))


@api_bp.delete("/tickets/<int:ticket_id>")
@protegido("Administrador")
def tickets_eliminar(ticket_id):
    srv.eliminar_ticket(srv.obtener_ticket(g.usuario, ticket_id))
    return "", 204


@api_bp.put("/tickets/<int:ticket_id>/asignar")
@protegido("Administrador")
def tickets_asignar(ticket_id):
    ticket = srv.asignar(srv.obtener_ticket(g.usuario, ticket_id), _json().get("tecnico_id"), g.usuario)
    return jsonify(ticket.to_dict(detalle=True))


@api_bp.put("/tickets/<int:ticket_id>/estado")
@protegido("Administrador", "Técnico")
def tickets_estado(ticket_id):
    datos = _json()
    ticket = srv.cambiar_estado(srv.obtener_ticket(g.usuario, ticket_id), datos.get("estado"),
                                datos.get("comentario"), g.usuario)
    return jsonify(ticket.to_dict(detalle=True))


@api_bp.get("/tickets/<int:ticket_id>/historial")
@protegido()
def tickets_historial(ticket_id):
    return jsonify([h.to_dict() for h in srv.obtener_ticket(g.usuario, ticket_id).historial])


@api_bp.post("/tickets/<int:ticket_id>/comentarios")
@protegido()
def tickets_comentar(ticket_id):
    ticket = srv.obtener_ticket(g.usuario, ticket_id)
    srv.comentar(ticket, _json().get("texto"), g.usuario)
    return jsonify(ticket.historial[-1].to_dict()), 201


# ---------------------------------------------------------------- notificaciones
@api_bp.get("/notificaciones")
@protegido()
def notificaciones_listar():
    consulta = Notificacion.query.filter_by(usuario_id=g.usuario.id)
    if request.args.get("no_leidas") == "true":
        consulta = consulta.filter_by(leido=False)
    return jsonify([n.to_dict() for n in consulta.order_by(Notificacion.created_at.desc()).limit(100)])


@api_bp.get("/notificaciones/contador")
@protegido()
def notificaciones_contador():
    return jsonify(no_leidas=srv.contar_no_leidas(g.usuario))


@api_bp.put("/notificaciones/<int:notif_id>/leida")
@protegido()
def notificaciones_leida(notif_id):
    notif = Notificacion.query.filter_by(id=notif_id, usuario_id=g.usuario.id).first_or_404()
    srv.marcar_leidas(g.usuario, [notif.id])
    return jsonify(id=notif.id, leido=True, no_leidas=srv.contar_no_leidas(g.usuario))


@api_bp.put("/notificaciones/leidas")
@protegido()
def notificaciones_todas():
    total = srv.marcar_leidas(g.usuario)
    return jsonify(marcadas=total, no_leidas=0)


# ---------------------------------------------------------------- reportes
@api_bp.get("/reportes/resumen")
@protegido()
def reportes_resumen():
    filtros = srv.filtros_reporte(request.args)
    return jsonify(filtros=filtros, **srv.resumen(g.usuario, _empresa(), filtros))


@api_bp.get("/reportes/<formato>")
@protegido()
def reportes_exportar(formato):
    if formato not in ("excel", "pdf"):
        return jsonify(error="Formato no disponible. Usa excel o pdf."), 404
    filtros = srv.filtros_reporte(request.args)
    tickets = srv.consulta_reporte(g.usuario, _empresa(), filtros).order_by(Ticket.created_at.desc()).all()
    subtitulo = descripcion_filtros(filtros, _empresa())
    nombre = f"reporte-tickets-{filtros['hasta']}"
    if formato == "excel":
        return send_file(generar_excel(tickets, subtitulo), as_attachment=True, download_name=nombre + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return send_file(generar_pdf(tickets, subtitulo, srv.resumen(g.usuario, _empresa(), filtros)),
                     as_attachment=True, download_name=nombre + ".pdf", mimetype="application/pdf")


@api_bp.get("/salud")
def salud():
    return jsonify(estado="ok", hora_servidor=iso(ahora()))
