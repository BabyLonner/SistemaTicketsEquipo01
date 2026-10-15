"""Páginas web (Jinja + Bootstrap)."""
import math
import os

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from flask_jwt_extended import get_current_user, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request
from sqlalchemy import func, or_

from . import servicios as srv
from .auth import emitir_token, protegido, revocar_token_actual
from .constantes import AREAS, CATEGORIAS, EMPRESAS, ESTADOS, PRIORIDADES, ROLES
from .errores import ErrorNegocio
from .extensions import db
from .models import Notificacion, Ticket, TicketFoto, Usuario
from .reportes import descripcion_filtros, generar_excel, generar_pdf
from .sla import HORAS_SLA

web_bp = Blueprint("web", __name__)


def _destino_seguro(url, defecto):
    return url if url and url.startswith("/") and not url.startswith("//") else defecto


def _empresa():
    return session.get("empresa", "")


# ---------------------------------------------------------------- sesión
@web_bp.get("/")
def inicio():
    return redirect(url_for("web.dashboard"))


@web_bp.route("/login", methods=["GET", "POST"])
def login():
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        if get_current_user():
            return redirect(url_for("web.dashboard"))
    except Exception:
        pass  # token vencido o inválido: se muestra el login

    error, correo = None, ""
    siguiente = request.values.get("next", "")
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        usuario = Usuario.query.filter(func.lower(Usuario.correo) == correo).first()
        if not correo or not clave:
            error = "Escribe tu correo y tu contraseña."
        elif usuario is None or not usuario.check_password(clave):
            error = "Correo o contraseña incorrectos."
        elif not usuario.activo:
            error = "Tu cuenta está desactivada. Pide al administrador que la active."
        else:
            token, max_age = emitir_token(usuario, bool(request.form.get("recordar")))
            respuesta = redirect(_destino_seguro(siguiente, url_for("web.dashboard")))
            set_access_cookies(respuesta, token, max_age=max_age)
            flash(f"Hola, {usuario.primer_nombre}.", "ok")
            return respuesta

    return render_template("auth/login.html", error=error, correo=correo, siguiente=siguiente,
                           demo=current_app.config["MOSTRAR_CUENTAS_DEMO"]), (401 if error else 200)


@web_bp.post("/logout")
@protegido()
def logout():
    revocar_token_actual()  # el token queda invalidado aunque alguien lo haya copiado
    respuesta = redirect(url_for("web.login"))
    unset_jwt_cookies(respuesta)
    flash("Cerraste sesión.", "ok")
    return respuesta


@web_bp.post("/empresa")
@protegido()
def elegir_empresa():
    empresa = request.form.get("empresa", "")
    if empresa in EMPRESAS:
        session["empresa"] = empresa
    else:
        session.pop("empresa", None)
    return redirect(_destino_seguro(request.form.get("volver"), url_for("web.dashboard")))


# ---------------------------------------------------------------- dashboard
@web_bp.get("/dashboard")
@protegido()
def dashboard():
    filtros = srv.filtros_reporte(request.args)
    datos = srv.resumen(g.usuario, _empresa(), filtros)
    return render_template("dashboard.html", seccion="dashboard", filtros=filtros, datos=datos, areas=AREAS,
                           tecnicos=Usuario.query.filter_by(rol="Técnico").order_by(Usuario.nombre).all())


@web_bp.get("/reportes/<formato>")
@protegido()
def exportar(formato):
    if formato not in ("excel", "pdf"):
        abort(404)
    filtros = srv.filtros_reporte(request.args)
    tickets = srv.consulta_reporte(g.usuario, _empresa(), filtros).order_by(Ticket.created_at.desc()).all()
    subtitulo = descripcion_filtros(filtros, _empresa())
    nombre = f"reporte-tickets-{filtros['hasta']}"
    if formato == "excel":
        return send_file(generar_excel(tickets, subtitulo), as_attachment=True, download_name=nombre + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    datos = srv.resumen(g.usuario, _empresa(), filtros)
    return send_file(generar_pdf(tickets, subtitulo, datos), as_attachment=True, download_name=nombre + ".pdf",
                     mimetype="application/pdf")


# ---------------------------------------------------------------- tickets
@web_bp.get("/tickets")
@protegido()
def tickets():
    filtros = {k: request.args.get(k, "") for k in ("q", "estado", "prioridad", "tecnico", "urgentes")}
    lista, alertas = srv.listar_tickets(g.usuario, _empresa(), filtros)

    por_pagina = current_app.config["TICKETS_POR_PAGINA"]
    paginas = max(1, math.ceil(len(lista) / por_pagina))
    pagina = min(max(request.args.get("pagina", 1, type=int), 1), paginas)
    inicio = (pagina - 1) * por_pagina

    def url_filtros(**cambios):
        params = {k: v for k, v in {**filtros, **cambios}.items() if v not in ("", None)}
        return url_for("web.tickets", **params)

    return render_template("tickets/lista.html", seccion="tickets", url_filtros=url_filtros, tickets=lista[inicio:inicio + por_pagina],
                           total_filtrados=len(lista), inicio=inicio, pagina=pagina, paginas=paginas,
                           alertas=alertas, filtros=filtros, estados=ESTADOS, prioridades=PRIORIDADES,
                           tecnicos=Usuario.query.filter_by(rol="Técnico").order_by(Usuario.nombre).all())


@web_bp.route("/tickets/nuevo", methods=["GET", "POST"])
@protegido()
def ticket_nuevo():
    errores, valores = {}, {"prioridad": "Media"}
    if request.method == "POST":
        valores = request.form.to_dict()
        try:
            ticket = srv.crear_ticket(g.usuario, valores, request.files.getlist("fotos"))
            flash(f"Ticket {ticket.codigo} creado.", "ok")
            return redirect(url_for("web.ticket_detalle", ticket_id=ticket.id))
        except ErrorNegocio as e:
            db.session.rollback()
            errores = e.campos or {"general": e.mensaje}
            if "fotos" in errores:
                errores["fotos"] = e.mensaje
    return render_template("tickets/nuevo.html", seccion="nuevo", errores=errores, valores=valores,
                           categorias=CATEGORIAS, prioridades=PRIORIDADES, horas_sla=HORAS_SLA,
                           max_fotos=current_app.config["MAX_FOTOS"]), (422 if errores else 200)


def _render_detalle(ticket, errores=None, valores=None, status=200):
    return render_template("tickets/detalle.html", seccion="tickets", t=ticket, errores=errores or {},
                           valores=valores or {}, estados=ESTADOS,
                           tecnicos=Usuario.query.filter_by(rol="Técnico", activo=True).order_by(Usuario.nombre).all(),
                           puede_asignar=g.usuario.rol == "Administrador",
                           puede_cambiar_estado=g.usuario.rol == "Administrador"
                           or (g.usuario.rol == "Técnico" and ticket.tecnico_id == g.usuario.id)), status


def _ticket_o_404(ticket_id):
    try:
        return srv.obtener_ticket(g.usuario, ticket_id)
    except ErrorNegocio:
        abort(404)


@web_bp.get("/tickets/<int:ticket_id>")
@protegido()
def ticket_detalle(ticket_id):
    return _render_detalle(_ticket_o_404(ticket_id))


@web_bp.post("/tickets/<int:ticket_id>/asignar")
@protegido("Administrador")
def ticket_asignar(ticket_id):
    ticket = _ticket_o_404(ticket_id)
    try:
        srv.asignar(ticket, request.form.get("tecnico_id"), g.usuario)
        flash(f"Ticket asignado a {ticket.tecnico.nombre}.", "ok")
    except ErrorNegocio as e:
        db.session.rollback()
        flash(e.mensaje, "error")
    return redirect(url_for("web.ticket_detalle", ticket_id=ticket.id))


@web_bp.post("/tickets/<int:ticket_id>/estado")
@protegido("Administrador", "Técnico")
def ticket_estado(ticket_id):
    ticket = _ticket_o_404(ticket_id)
    nuevo = request.form.get("estado", "")
    try:
        srv.cambiar_estado(ticket, nuevo, request.form.get("comentario"), g.usuario)
    except ErrorNegocio as e:
        db.session.rollback()
        if e.status == 403:
            flash(e.mensaje, "error")
            return redirect(url_for("web.ticket_detalle", ticket_id=ticket.id))
        return _render_detalle(ticket, errores=e.campos, valores=request.form.to_dict(), status=422)
    flash(f"Estado actualizado a {nuevo}.", "ok")
    return redirect(url_for("web.ticket_detalle", ticket_id=ticket.id))


@web_bp.post("/tickets/<int:ticket_id>/comentarios")
@protegido()
def ticket_comentar(ticket_id):
    ticket = _ticket_o_404(ticket_id)
    try:
        srv.comentar(ticket, request.form.get("texto"), g.usuario)
    except ErrorNegocio as e:
        db.session.rollback()
        return _render_detalle(ticket, errores={"texto": e.mensaje}, valores=request.form.to_dict(), status=422)
    flash("Comentario publicado.", "ok")
    return redirect(url_for("web.ticket_detalle", ticket_id=ticket.id, _anchor="linea-tiempo"))


@web_bp.get("/uploads/<path:archivo>")
@protegido()
def uploads(archivo):
    foto = TicketFoto.query.filter(or_(TicketFoto.archivo == archivo, TicketFoto.miniatura == archivo)).first()
    if foto is None or not srv.puede_ver(g.usuario, foto.ticket):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], os.path.basename(archivo), max_age=3600)


# ---------------------------------------------------------------- notificaciones
@web_bp.get("/notificaciones")
@protegido()
def notificaciones():
    filtro = "noleidas" if request.args.get("filtro") == "noleidas" else "todas"
    consulta = Notificacion.query.filter_by(usuario_id=g.usuario.id)
    if filtro == "noleidas":
        consulta = consulta.filter_by(leido=False)
    lista = consulta.order_by(Notificacion.created_at.desc()).limit(100).all()
    return render_template("notificaciones.html", seccion="", lista=lista, filtro=filtro,
                           sin_leer=srv.contar_no_leidas(g.usuario))


@web_bp.post("/notificaciones/<int:notif_id>/leida")
@protegido()
def notificacion_leida(notif_id):
    srv.marcar_leidas(g.usuario, [notif_id])
    return redirect(_destino_seguro(request.form.get("volver"), url_for("web.notificaciones")))


@web_bp.get("/notificaciones/<int:notif_id>/abrir")
@protegido()
def notificacion_abrir(notif_id):
    notif = Notificacion.query.filter_by(id=notif_id, usuario_id=g.usuario.id).first_or_404()
    srv.marcar_leidas(g.usuario, [notif.id])
    return redirect(url_for("web.ticket_detalle", ticket_id=notif.referencia_ticket))


@web_bp.post("/notificaciones/leidas")
@protegido()
def notificaciones_todas_leidas():
    srv.marcar_leidas(g.usuario)
    flash("Todas las notificaciones quedaron como leídas.", "ok")
    return redirect(url_for("web.notificaciones"))


# ---------------------------------------------------------------- usuarios
def _render_usuarios(errores=None, valores=None, editando=None, status=200):
    q = request.args.get("q", "").strip().lower()
    rol = request.args.get("rol", "")
    estado = request.args.get("estado", "")
    consulta = Usuario.query
    if q:
        consulta = consulta.filter(or_(func.lower(Usuario.nombre).contains(q), func.lower(Usuario.correo).contains(q)))
    if rol in ROLES:
        consulta = consulta.filter_by(rol=rol)
    if estado in ("activo", "inactivo"):
        consulta = consulta.filter_by(activo=estado == "activo")
    if _empresa():
        consulta = consulta.filter_by(empresa=_empresa())

    if editando and not valores:
        valores = editando.to_dict()
    return render_template("usuarios.html", seccion="usuarios", lista=consulta.order_by(Usuario.nombre).all(),
                           errores=errores or {}, valores=valores or {"activo": True}, editando=editando,
                           roles=ROLES, areas=AREAS, filtros={"q": q, "rol": rol, "estado": estado}), status


@web_bp.get("/usuarios")
@protegido("Administrador")
def usuarios():
    editar = request.args.get("editar", type=int)
    editando = db.session.get(Usuario, editar) if editar else None
    return _render_usuarios(editando=editando)


@web_bp.post("/usuarios")
@protegido("Administrador")
def usuario_crear():
    datos = request.form.to_dict()
    datos["activo"] = "activo" in request.form
    try:
        usuario = srv.crear_usuario(datos)
    except ErrorNegocio as e:
        db.session.rollback()
        return _render_usuarios(errores=e.campos, valores=request.form.to_dict(), status=422)
    flash(f"{usuario.nombre} quedó registrado como {usuario.rol.lower()}.", "ok")
    return redirect(url_for("web.usuarios"))


@web_bp.post("/usuarios/<int:usuario_id>")
@protegido("Administrador")
def usuario_actualizar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    datos = request.form.to_dict()
    datos["activo"] = "activo" in request.form
    try:
        srv.actualizar_usuario(usuario, datos, g.usuario)
    except ErrorNegocio as e:
        db.session.rollback()
        errores = e.campos or {"general": e.mensaje}
        return _render_usuarios(errores=errores, valores=request.form.to_dict(), editando=usuario, status=422)
    flash(f"Cambios guardados para {usuario.nombre}.", "ok")
    return redirect(url_for("web.usuarios"))


@web_bp.post("/usuarios/<int:usuario_id>/estado")
@protegido("Administrador")
def usuario_estado(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    try:
        srv.cambiar_activo(usuario, not usuario.activo, g.usuario)
        flash(f"{usuario.nombre} quedó {'activo' if usuario.activo else 'inactivo'}.", "ok")
    except ErrorNegocio as e:
        flash(e.mensaje, "error")
    return redirect(_destino_seguro(request.form.get("volver"), url_for("web.usuarios")))
