import math
import os
from datetime import datetime

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   send_from_directory, session, url_for)
from flask_jwt_extended import get_current_user, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request

import controlador_notificaciones
import controlador_reportes
import controlador_tickets
import controlador_usuarios
from api import registrar_api
from seguridad import configurar_jwt, crear_token, requiere_sesion, revocar_token_actual
from utilidades import (AREAS, CARPETA_UPLOADS, CATEGORIAS, EMPRESAS, ESTADOS, HORAS_SLA, MAX_FOTOS, PRIORIDADES,
                        ROLES, ErrorNegocio, duracion)

app = Flask(__name__)

# Cambia estas claves por textos largos y secretos antes de entregar
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "cambia-esta-clave-secreta")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "cambia-esta-otra-clave-secreta")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # tamaño máximo de un envío (fotos)

CORREO_SOPORTE = "soporte@empresa.pe"
MOSTRAR_CUENTAS_DEMO = True   # pon False para ocultar los botones de prueba del login
TICKETS_POR_PAGINA = 10

configurar_jwt(app)
registrar_api(app)


# ---------------------------------------------
# Datos disponibles en todas las plantillas
# ---------------------------------------------
@app.context_processor
def variables_globales():
    usuario = g.get("usuario")
    menu = []
    if usuario:
        menu = [("dashboard", "Dashboard", "dashboard"), ("tickets", "Tickets", "tickets"),
                ("nuevo", "Nuevo ticket", "nuevo_ticket")]
        if usuario["rol"] == "Administrador":
            menu.append(("usuarios", "Usuarios", "usuarios"))
    return {
        "usuario": usuario,
        "menu": menu,
        "notif_pendientes": controlador_notificaciones.contar_no_leidas(usuario["id"]) if usuario else 0,
        "empresas": EMPRESAS,
        "empresa_actual": session.get("empresa", ""),
        "csrf_token": request.cookies.get("csrf_access_token", ""),
        "correo_soporte": CORREO_SOPORTE,
        "version": "v1.0.0",
        "anio": datetime.now().year,
    }


@app.template_filter("fecha")
def filtro_fecha(valor):
    return valor.strftime("%d/%m/%Y · %H:%M") if valor else "—"


@app.template_filter("fecha_corta")
def filtro_fecha_corta(valor):
    return valor.strftime("%d/%m · %H:%M") if valor else "—"


@app.template_filter("iso")
def filtro_iso(valor):
    return valor.isoformat() if valor else ""


app.add_template_filter(duracion, "duracion")


def empresa_actual():
    return session.get("empresa", "")


def destino_seguro(url, defecto):
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return defecto


def obtener_ticket_o_404(ticket_id):
    try:
        return controlador_tickets.obtener(g.usuario, ticket_id)
    except ErrorNegocio:
        abort(404)


# ---------------------------------------------
# Módulo 1: inicio y cierre de sesión
# ---------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/login")
def login():
    try:
        verify_jwt_in_request(optional=True, locations=["cookies"])
        if get_current_user():
            return redirect(url_for("dashboard"))
    except Exception:
        pass   # token vencido o inválido: se muestra el login
    return render_template("login.html", siguiente=request.args.get("next", ""), demo=MOSTRAR_CUENTAS_DEMO)


@app.route("/procesar_login", methods=["POST"])
def procesar_login():
    """Recibe el formulario por fetch (static/js/app.js) y responde en JSON."""
    try:
        v_email = request.form.get("email", "").strip()
        v_passw = request.form.get("password", "")
        if not v_email or not v_passw:
            return jsonify(exito=False, mensaje="Escribe tu correo y tu contraseña."), 400

        usuario = controlador_usuarios.verificar_credenciales(v_email, v_passw)
        if usuario is None:
            return jsonify(exito=False, mensaje="Correo o contraseña incorrectos."), 401
        if not usuario["activo"]:
            return jsonify(exito=False, mensaje="Tu cuenta está desactivada. Pide al administrador que la active."), 403

        token, max_age = crear_token(usuario, request.form.get("recordar") == "1")
        destino = destino_seguro(request.form.get("next"), url_for("dashboard"))
        respuesta = jsonify(exito=True, mensaje="Bienvenido, " + usuario["primer_nombre"] + ".", redirigir=destino)
        set_access_cookies(respuesta, token, max_age=max_age)
        flash("Hola, " + usuario["primer_nombre"] + ".", "ok")
        return respuesta
    except Exception as e:
        return jsonify(exito=False, mensaje="Error de conexión con la base de datos: " + repr(e)), 500


@app.route("/cerrar_sesion", methods=["POST"])
@requiere_sesion()
def cerrar_sesion():
    revocar_token_actual()
    respuesta = redirect(url_for("login"))
    unset_jwt_cookies(respuesta)
    flash("Cerraste sesión.", "ok")
    return respuesta


@app.route("/elegir_empresa", methods=["POST"])
@requiere_sesion()
def elegir_empresa():
    empresa = request.form.get("empresa", "")
    if empresa in EMPRESAS:
        session["empresa"] = empresa
    else:
        session.pop("empresa", None)
    return redirect(destino_seguro(request.form.get("volver"), url_for("dashboard")))


# ---------------------------------------------
# Módulo 6: dashboard y reportes
# ---------------------------------------------
@app.route("/dashboard")
@requiere_sesion()
def dashboard():
    filtros = controlador_reportes.filtros_desde(request.args)
    datos = controlador_reportes.resumen(g.usuario, empresa_actual(), filtros)
    return render_template("dashboard.html", seccion="dashboard", filtros=filtros, datos=datos, areas=AREAS,
                           tecnicos=controlador_usuarios.listar_tecnicos())


@app.route("/exportar_excel")
@requiere_sesion()
def exportar_excel():
    filtros = controlador_reportes.filtros_desde(request.args)
    tickets = controlador_reportes.tickets_reporte(g.usuario, empresa_actual(), filtros)
    archivo = controlador_reportes.generar_excel(tickets, controlador_reportes.descripcion_filtros(filtros, empresa_actual()))
    return send_file(archivo, as_attachment=True, download_name="reporte-tickets-" + filtros["hasta"] + ".xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/exportar_pdf")
@requiere_sesion()
def exportar_pdf():
    filtros = controlador_reportes.filtros_desde(request.args)
    tickets = controlador_reportes.tickets_reporte(g.usuario, empresa_actual(), filtros)
    datos = controlador_reportes.resumen(g.usuario, empresa_actual(), filtros)
    archivo = controlador_reportes.generar_pdf(tickets, controlador_reportes.descripcion_filtros(filtros, empresa_actual()), datos)
    return send_file(archivo, as_attachment=True, download_name="reporte-tickets-" + filtros["hasta"] + ".pdf",
                     mimetype="application/pdf")


# ---------------------------------------------
# Módulos 2, 3 y 4: tickets
# ---------------------------------------------
@app.route("/tickets")
@requiere_sesion()
def tickets():
    filtros = {k: request.args.get(k, "") for k in ("q", "estado", "prioridad", "tecnico", "urgentes")}
    lista, alertas = controlador_tickets.listar(g.usuario, empresa_actual(), filtros)

    paginas = max(1, math.ceil(len(lista) / TICKETS_POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int), 1), paginas)
    inicio = (pagina - 1) * TICKETS_POR_PAGINA

    def url_filtros(**cambios):
        parametros = {k: v for k, v in {**filtros, **cambios}.items() if v not in ("", None)}
        return url_for("tickets", **parametros)

    return render_template("tickets.html", seccion="tickets", tickets=lista[inicio:inicio + TICKETS_POR_PAGINA],
                           total_filtrados=len(lista), inicio=inicio, pagina=pagina, paginas=paginas,
                           alertas=alertas, filtros=filtros, url_filtros=url_filtros, estados=ESTADOS,
                           prioridades=PRIORIDADES, tecnicos=controlador_usuarios.listar_tecnicos())


def mostrar_nuevo_ticket(errores=None, valores=None, status=200):
    return render_template("nuevo_ticket.html", seccion="nuevo", errores=errores or {},
                           valores=valores or {"prioridad": "Media"}, categorias=CATEGORIAS,
                           prioridades=PRIORIDADES, horas_sla=HORAS_SLA, max_fotos=MAX_FOTOS), status


@app.route("/nuevo_ticket")
@requiere_sesion()
def nuevo_ticket():
    return mostrar_nuevo_ticket()


@app.route("/guardar_ticket", methods=["POST"])
@requiere_sesion()
def guardar_ticket():
    try:
        ticket_id = controlador_tickets.crear(g.usuario, request.form, request.files.getlist("fotos"))
    except ErrorNegocio as e:
        errores = e.campos or {"general": e.mensaje}
        if "fotos" in errores:
            errores["fotos"] = e.mensaje
        return mostrar_nuevo_ticket(errores, request.form.to_dict(), 422)
    flash("Ticket TK-" + str(ticket_id).zfill(4) + " creado.", "ok")
    return redirect(url_for("detalle_ticket", ticket_id=ticket_id))


def mostrar_detalle(ticket, errores=None, valores=None, status=200):
    puede_cambiar = g.usuario["rol"] == "Administrador" or (
        g.usuario["rol"] == "Técnico" and ticket["tecnico_id"] == g.usuario["id"])
    return render_template("detalle_ticket.html", seccion="tickets", t=ticket, errores=errores or {},
                           valores=valores or {}, estados=ESTADOS,
                           tecnicos=controlador_usuarios.listar_tecnicos(solo_activos=True),
                           puede_asignar=g.usuario["rol"] == "Administrador",
                           puede_cambiar_estado=puede_cambiar), status


@app.route("/detalle_ticket/<int:ticket_id>")
@requiere_sesion()
def detalle_ticket(ticket_id):
    return mostrar_detalle(obtener_ticket_o_404(ticket_id))


@app.route("/asignar_ticket/<int:ticket_id>", methods=["POST"])
@requiere_sesion("Administrador")
def asignar_ticket(ticket_id):
    ticket = obtener_ticket_o_404(ticket_id)
    try:
        tecnico = controlador_tickets.asignar(ticket, request.form.get("tecnico_id"), g.usuario)
        flash("Ticket asignado a " + tecnico["nombre"] + ".", "ok")
    except ErrorNegocio as e:
        flash(e.mensaje, "error")
    return redirect(url_for("detalle_ticket", ticket_id=ticket_id))


@app.route("/cambiar_estado/<int:ticket_id>", methods=["POST"])
@requiere_sesion("Administrador", "Técnico")
def cambiar_estado(ticket_id):
    ticket = obtener_ticket_o_404(ticket_id)
    nuevo = request.form.get("estado", "")
    try:
        controlador_tickets.cambiar_estado(ticket, nuevo, request.form.get("comentario"), g.usuario)
    except ErrorNegocio as e:
        if e.status == 403:
            flash(e.mensaje, "error")
            return redirect(url_for("detalle_ticket", ticket_id=ticket_id))
        return mostrar_detalle(ticket, e.campos, request.form.to_dict(), 422)
    flash("Estado actualizado a " + nuevo + ".", "ok")
    return redirect(url_for("detalle_ticket", ticket_id=ticket_id))


@app.route("/comentar_ticket/<int:ticket_id>", methods=["POST"])
@requiere_sesion()
def comentar_ticket(ticket_id):
    ticket = obtener_ticket_o_404(ticket_id)
    try:
        controlador_tickets.comentar(ticket, request.form.get("texto"), g.usuario)
    except ErrorNegocio as e:
        return mostrar_detalle(ticket, {"texto": e.mensaje}, request.form.to_dict(), 422)
    flash("Comentario publicado.", "ok")
    return redirect(url_for("detalle_ticket", ticket_id=ticket_id, _anchor="linea-tiempo"))


@app.route("/uploads/<nombre>")
@requiere_sesion()
def ver_foto(nombre):
    """Las fotos no están en /static: solo las ve quien puede ver el ticket."""
    foto = controlador_tickets.foto_por_archivo(nombre)
    if foto is None or not controlador_tickets.puede_ver(g.usuario, foto):
        abort(404)
    return send_from_directory(CARPETA_UPLOADS, nombre, max_age=3600)


# ---------------------------------------------
# Módulo 5: notificaciones
# ---------------------------------------------
@app.route("/notificaciones")
@requiere_sesion()
def notificaciones():
    filtro = "noleidas" if request.args.get("filtro") == "noleidas" else "todas"
    lista = controlador_notificaciones.listar(g.usuario["id"], solo_no_leidas=filtro == "noleidas")
    return render_template("notificaciones.html", seccion="", lista=lista, filtro=filtro,
                           sin_leer=controlador_notificaciones.contar_no_leidas(g.usuario["id"]))


@app.route("/abrir_notificacion/<int:notificacion_id>")
@requiere_sesion()
def abrir_notificacion(notificacion_id):
    notificacion = controlador_notificaciones.obtener(g.usuario["id"], notificacion_id)
    if notificacion is None:
        abort(404)
    controlador_notificaciones.marcar_leidas(g.usuario["id"], [notificacion_id])
    return redirect(url_for("detalle_ticket", ticket_id=notificacion["referencia_ticket"]))


@app.route("/marcar_notificacion/<int:notificacion_id>", methods=["POST"])
@requiere_sesion()
def marcar_notificacion(notificacion_id):
    controlador_notificaciones.marcar_leidas(g.usuario["id"], [notificacion_id])
    return redirect(destino_seguro(request.form.get("volver"), url_for("notificaciones")))


@app.route("/marcar_todas", methods=["POST"])
@requiere_sesion()
def marcar_todas():
    controlador_notificaciones.marcar_leidas(g.usuario["id"])
    flash("Todas las notificaciones quedaron como leídas.", "ok")
    return redirect(url_for("notificaciones"))


# ---------------------------------------------
# Módulo 1: gestión de usuarios (solo administrador)
# ---------------------------------------------
def mostrar_usuarios(errores=None, valores=None, editando=None, status=200):
    filtros = {"q": request.args.get("q", "").strip(), "rol": request.args.get("rol", ""),
               "estado": request.args.get("estado", "")}
    lista = controlador_usuarios.listar(filtros["q"], filtros["rol"], filtros["estado"], empresa_actual())
    if editando and not valores:
        valores = editando
    return render_template("usuarios.html", seccion="usuarios", lista=lista, errores=errores or {},
                           valores=valores or {"activo": True}, editando=editando, roles=ROLES, areas=AREAS,
                           filtros=filtros), status


@app.route("/usuarios")
@requiere_sesion("Administrador")
def usuarios():
    editar = request.args.get("editar", type=int)
    editando = controlador_usuarios.obtener_por_id(editar) if editar else None
    return mostrar_usuarios(editando=editando)


@app.route("/guardar_usuario", methods=["POST"])
@requiere_sesion("Administrador")
def guardar_usuario():
    datos = request.form.to_dict()
    datos["activo"] = "activo" in request.form
    try:
        usuario = controlador_usuarios.crear(datos)
    except ErrorNegocio as e:
        return mostrar_usuarios(e.campos, datos, status=422)
    flash(usuario["nombre"] + " quedó registrado como " + usuario["rol"].lower() + ".", "ok")
    return redirect(url_for("usuarios"))


@app.route("/actualizar_usuario/<int:usuario_id>", methods=["POST"])
@requiere_sesion("Administrador")
def actualizar_usuario(usuario_id):
    usuario = controlador_usuarios.obtener_por_id(usuario_id)
    if usuario is None:
        abort(404)
    datos = request.form.to_dict()
    datos["activo"] = "activo" in request.form
    try:
        controlador_usuarios.actualizar(usuario_id, datos, g.usuario)
    except ErrorNegocio as e:
        return mostrar_usuarios(e.campos or {"general": e.mensaje}, datos, usuario, 422)
    flash("Cambios guardados para " + datos["nombre"].strip() + ".", "ok")
    return redirect(url_for("usuarios"))


@app.route("/cambiar_estado_usuario/<int:usuario_id>", methods=["POST"])
@requiere_sesion("Administrador")
def cambiar_estado_usuario(usuario_id):
    usuario = controlador_usuarios.obtener_por_id(usuario_id)
    if usuario is None:
        abort(404)
    try:
        usuario = controlador_usuarios.cambiar_activo(usuario_id, not usuario["activo"], g.usuario)
        flash(usuario["nombre"] + (" quedó activo." if usuario["activo"] else " quedó inactivo."), "ok")
    except ErrorNegocio as e:
        flash(e.mensaje, "error")
    return redirect(destino_seguro(request.form.get("volver"), url_for("usuarios")))


# ---------------------------------------------
# Páginas de error
# ---------------------------------------------
MENSAJES_ERROR = {
    403: ("No tienes acceso a esta página", "Tu perfil no tiene permiso para ver esto."),
    404: ("No encontramos esta página", "Revisa la dirección o vuelve al inicio."),
    413: ("El archivo es demasiado grande", "Las fotos deben pesar menos de 5 MB cada una."),
    500: ("Algo falló en el servidor", "Revisa que MySQL esté encendido e inténtalo de nuevo."),
}


def pagina_error(error):
    codigo = getattr(error, "code", 500) or 500
    titulo, detalle = MENSAJES_ERROR.get(codigo, MENSAJES_ERROR[500])
    if request.path.startswith("/api/"):
        return jsonify(error=titulo), codigo
    return render_template("error.html", codigo=codigo, titulo=titulo, detalle=detalle), codigo


for codigo_error in MENSAJES_ERROR:
    app.register_error_handler(codigo_error, pagina_error)


if __name__ == "__main__":
    app.run(debug=True)
