"""Filtros de Jinja y variables disponibles en todas las plantillas."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app, g, request, session

from .constantes import EMPRESAS
from .models import iso
from .servicios import contar_no_leidas
from .sla import duracion


def registrar(app):
    def a_local(dt):
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(app.config["ZONA_HORARIA"]))

    @app.template_filter("fecha")
    def fecha(dt):
        return a_local(dt).strftime("%d/%m/%Y · %H:%M") if dt else "—"

    @app.template_filter("fecha_corta")
    def fecha_corta(dt):
        return a_local(dt).strftime("%d/%m · %H:%M") if dt else "—"

    app.add_template_filter(iso, "iso")
    app.add_template_filter(duracion, "duracion")

    @app.context_processor
    def variables_globales():
        usuario = g.get("usuario")
        menu = []
        if usuario:
            menu = [("dashboard", "Dashboard", "web.dashboard"),
                    ("tickets", "Tickets", "web.tickets"),
                    ("nuevo", "Nuevo ticket", "web.ticket_nuevo")]
            if usuario.rol == "Administrador":
                menu.append(("usuarios", "Usuarios", "web.usuarios"))
        return {
            "usuario": usuario,
            "menu": menu,
            "notif_pendientes": contar_no_leidas(usuario) if usuario else 0,
            "empresas": EMPRESAS,
            "empresa_actual": session.get("empresa", ""),
            "csrf_token": request.cookies.get(current_app.config["JWT_ACCESS_CSRF_COOKIE_NAME"], ""),
            "correo_soporte": current_app.config["CORREO_SOPORTE"],
            "version": "v1.0.0",
            "anio": datetime.now().year,
        }
