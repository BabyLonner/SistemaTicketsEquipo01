"""API REST (módulo 6). Todas las rutas, salvo el login, piden el header:
    Authorization: Bearer <token>
Respuestas en JSON con los códigos HTTP correctos.
"""
import math

from flask import flash, g, jsonify, redirect, request, send_file, url_for

import controlador_notificaciones
import controlador_reportes
import controlador_tickets
import controlador_usuarios
from seguridad import DURACION_TOKEN, crear_token, requiere_sesion, revocar_token_actual
from utilidades import ErrorNegocio, ahora


def registrar_api(app):

    @app.errorhandler(ErrorNegocio)
    def error_negocio(e):
        """Errores de validación: en la API se responden en JSON; en la web, con un aviso."""
        if not request.path.startswith("/api/"):
            flash(e.mensaje, "error")
            return redirect(request.referrer or url_for("dashboard"))
        cuerpo = {"error": e.mensaje}
        if e.campos:
            cuerpo["campos"] = e.campos
        return jsonify(cuerpo), e.status

    def datos_json():
        return request.get_json(silent=True) or {}

    def empresa():
        return request.args.get("empresa", "")

    # ---------------- Autenticación ----------------
    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        datos = datos_json()
        usuario = controlador_usuarios.verificar_credenciales(datos.get("email") or "", datos.get("password") or "")
        if usuario is None:
            return jsonify(error="Correo o contraseña incorrectos."), 401
        if not usuario["activo"]:
            return jsonify(error="La cuenta está desactivada."), 403
        token, _ = crear_token(usuario)
        return jsonify(access_token=token, token_type="Bearer", expires_in=int(DURACION_TOKEN.total_seconds()),
                       usuario=controlador_usuarios.a_json(usuario))

    @app.route("/api/auth/logout", methods=["POST"])
    @requiere_sesion()
    def api_logout():
        revocar_token_actual()
        return jsonify(mensaje="Sesión cerrada. El token ya no es válido.")

    @app.route("/api/auth/yo")
    @requiere_sesion()
    def api_yo():
        return jsonify(controlador_usuarios.a_json(g.usuario))

    # ---------------- Usuarios (solo administrador) ----------------
    @app.route("/api/usuarios")
    @requiere_sesion("Administrador")
    def api_usuarios_listar():
        estado = {"true": "activo", "false": "inactivo"}.get(request.args.get("activo"), "")
        lista = controlador_usuarios.listar(request.args.get("q", ""), request.args.get("rol", ""), estado, empresa())
        return jsonify([controlador_usuarios.a_json(u) for u in lista])

    @app.route("/api/usuarios", methods=["POST"])
    @requiere_sesion("Administrador")
    def api_usuarios_crear():
        return jsonify(controlador_usuarios.a_json(controlador_usuarios.crear(datos_json()))), 201

    def usuario_o_404(usuario_id):
        usuario = controlador_usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise ErrorNegocio("No existe ese usuario.", 404)
        return usuario

    @app.route("/api/usuarios/<int:usuario_id>")
    @requiere_sesion("Administrador")
    def api_usuarios_ver(usuario_id):
        return jsonify(controlador_usuarios.a_json(usuario_o_404(usuario_id)))

    @app.route("/api/usuarios/<int:usuario_id>", methods=["PUT"])
    @requiere_sesion("Administrador")
    def api_usuarios_actualizar(usuario_id):
        actual = usuario_o_404(usuario_id)
        datos = {**actual, **datos_json()}   # solo cambia lo que se envía
        if "password" not in datos_json():
            datos["password"] = ""
        return jsonify(controlador_usuarios.a_json(controlador_usuarios.actualizar(usuario_id, datos, g.usuario)))

    @app.route("/api/usuarios/<int:usuario_id>", methods=["DELETE"])
    @requiere_sesion("Administrador")
    def api_usuarios_desactivar(usuario_id):
        """No borra el registro (sus tickets lo referencian): lo desactiva."""
        usuario_o_404(usuario_id)
        return jsonify(controlador_usuarios.a_json(controlador_usuarios.cambiar_activo(usuario_id, False, g.usuario)))

    # ---------------- Tickets ----------------
    @app.route("/api/tickets")
    @requiere_sesion()
    def api_tickets_listar():
        filtros = {k: request.args.get(k, "") for k in ("q", "estado", "prioridad", "tecnico", "urgentes")}
        lista, alertas = controlador_tickets.listar(g.usuario, empresa(), filtros)
        por_pagina = min(max(request.args.get("por_pagina", 20, type=int), 1), 100)
        pagina = max(request.args.get("pagina", 1, type=int), 1)
        inicio = (pagina - 1) * por_pagina
        return jsonify(datos=[controlador_tickets.a_json(t) for t in lista[inicio:inicio + por_pagina]],
                       pagina=pagina, por_pagina=por_pagina, total=len(lista),
                       paginas=max(1, math.ceil(len(lista) / por_pagina)), alertas=alertas)

    @app.route("/api/tickets", methods=["POST"])
    @requiere_sesion()
    def api_tickets_crear():
        """Acepta JSON o multipart/form-data (campo 'fotos', hasta 3 imágenes)."""
        if request.content_type and request.content_type.startswith("multipart/"):
            ticket_id = controlador_tickets.crear(g.usuario, request.form, request.files.getlist("fotos"))
        else:
            ticket_id = controlador_tickets.crear(g.usuario, datos_json())
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True)), 201

    @app.route("/api/tickets/<int:ticket_id>")
    @requiere_sesion()
    def api_tickets_ver(ticket_id):
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True))

    @app.route("/api/tickets/<int:ticket_id>", methods=["PUT"])
    @requiere_sesion()
    def api_tickets_actualizar(ticket_id):
        controlador_tickets.actualizar(controlador_tickets.obtener(g.usuario, ticket_id), datos_json(), g.usuario)
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True))

    @app.route("/api/tickets/<int:ticket_id>", methods=["DELETE"])
    @requiere_sesion("Administrador")
    def api_tickets_eliminar(ticket_id):
        controlador_tickets.eliminar(controlador_tickets.obtener(g.usuario, ticket_id))
        return "", 204

    @app.route("/api/tickets/<int:ticket_id>/asignar", methods=["PUT"])
    @requiere_sesion("Administrador")
    def api_tickets_asignar(ticket_id):
        ticket = controlador_tickets.obtener(g.usuario, ticket_id)
        controlador_tickets.asignar(ticket, datos_json().get("tecnico_id"), g.usuario)
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True))

    @app.route("/api/tickets/<int:ticket_id>/estado", methods=["PUT"])
    @requiere_sesion("Administrador", "Técnico")
    def api_tickets_estado(ticket_id):
        datos = datos_json()
        ticket = controlador_tickets.obtener(g.usuario, ticket_id)
        controlador_tickets.cambiar_estado(ticket, datos.get("estado"), datos.get("comentario"), g.usuario)
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True))

    @app.route("/api/tickets/<int:ticket_id>/historial")
    @requiere_sesion()
    def api_tickets_historial(ticket_id):
        return jsonify(controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True)["historial"])

    @app.route("/api/tickets/<int:ticket_id>/comentarios", methods=["POST"])
    @requiere_sesion()
    def api_tickets_comentar(ticket_id):
        ticket = controlador_tickets.obtener(g.usuario, ticket_id)
        controlador_tickets.comentar(ticket, datos_json().get("texto"), g.usuario)
        historial = controlador_tickets.a_json(controlador_tickets.obtener(g.usuario, ticket_id), True)["historial"]
        return jsonify(historial[-1]), 201

    # ---------------- Notificaciones ----------------
    @app.route("/api/notificaciones")
    @requiere_sesion()
    def api_notificaciones_listar():
        lista = controlador_notificaciones.listar(g.usuario["id"], request.args.get("no_leidas") == "true")
        return jsonify([controlador_notificaciones.a_json(n) for n in lista])

    @app.route("/api/notificaciones/contador")
    @requiere_sesion()
    def api_notificaciones_contador():
        return jsonify(no_leidas=controlador_notificaciones.contar_no_leidas(g.usuario["id"]))

    @app.route("/api/notificaciones/<int:notificacion_id>/leida", methods=["PUT"])
    @requiere_sesion()
    def api_notificaciones_leida(notificacion_id):
        if controlador_notificaciones.obtener(g.usuario["id"], notificacion_id) is None:
            raise ErrorNegocio("No existe esa notificación.", 404)
        controlador_notificaciones.marcar_leidas(g.usuario["id"], [notificacion_id])
        return jsonify(id=notificacion_id, leido=True,
                       no_leidas=controlador_notificaciones.contar_no_leidas(g.usuario["id"]))

    @app.route("/api/notificaciones/leidas", methods=["PUT"])
    @requiere_sesion()
    def api_notificaciones_todas():
        total = controlador_notificaciones.marcar_leidas(g.usuario["id"])
        return jsonify(marcadas=total, no_leidas=0)

    # ---------------- Reportes ----------------
    @app.route("/api/reportes/resumen")
    @requiere_sesion()
    def api_reportes_resumen():
        filtros = controlador_reportes.filtros_desde(request.args)
        return jsonify(filtros=filtros, **controlador_reportes.resumen(g.usuario, empresa(), filtros))

    @app.route("/api/reportes/<formato>")
    @requiere_sesion()
    def api_reportes_exportar(formato):
        if formato not in ("excel", "pdf"):
            return jsonify(error="Formato no disponible. Usa excel o pdf."), 404
        filtros = controlador_reportes.filtros_desde(request.args)
        tickets = controlador_reportes.tickets_reporte(g.usuario, empresa(), filtros)
        subtitulo = controlador_reportes.descripcion_filtros(filtros, empresa())
        nombre = "reporte-tickets-" + filtros["hasta"]
        if formato == "excel":
            return send_file(controlador_reportes.generar_excel(tickets, subtitulo), as_attachment=True,
                             download_name=nombre + ".xlsx",
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        datos = controlador_reportes.resumen(g.usuario, empresa(), filtros)
        return send_file(controlador_reportes.generar_pdf(tickets, subtitulo, datos), as_attachment=True,
                         download_name=nombre + ".pdf", mimetype="application/pdf")

    @app.route("/api/salud")
    def api_salud():
        return jsonify(estado="ok", hora_servidor=ahora().isoformat())
