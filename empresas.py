"""
Gestión de empresas — SOLO SUPERUSUARIO.

* Crear una empresa crea también su dominio de correo, sus áreas y su
  usuario Administrador (que desde ahí controla a sus trabajadores).
* "Administrar" deja al superusuario trabajando dentro de esa empresa
  (tickets, asignación, SLA, reportes y usuarios) con permisos de administrador.
* Activar/desactivar o eliminar la empresa con todos sus datos.
"""
import os
import shutil

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

import config
from auth import ROL_SUPER, hashear, llenar_sesion, roles_requeridos, validar_clave_nueva
from db import conexion, consultar
from utils import COLOR_RE, DOMINIO_RE, ahora, correo_valido, dominio_de, slug

empresas_bp = Blueprint("empresas", __name__)

AREAS_POR_DEFECTO = "TI, Administración, Contabilidad, Recursos Humanos, Operaciones, Logística"

SQL_EMPRESAS = """
    SELECT e.*, MIN(d.dominio) AS dominio,
           (SELECT COUNT(*) FROM users u WHERE u.empresa_id = e.id) AS total_usuarios,
           (SELECT COUNT(*) FROM tickets t WHERE t.empresa_id = e.id) AS total_tickets,
           (SELECT u.nombre FROM users u WHERE u.empresa_id = e.id AND u.rol = 'Administrador'
             ORDER BY u.id LIMIT 1) AS administrador,
           (SELECT u.correo FROM users u WHERE u.empresa_id = e.id AND u.rol = 'Administrador'
             ORDER BY u.id LIMIT 1) AS administrador_correo
      FROM empresas e
      LEFT JOIN empresa_dominios d ON d.empresa_id = e.id
"""


def _empresa_o_404(empresa_id):
    fila = consultar(SQL_EMPRESAS + " WHERE e.id = %s GROUP BY e.id", (empresa_id,), uno=True)
    if not fila:
        abort(404)
    return fila


def _validar(datos):
    errores = {}
    nombre = " ".join((datos.get("nombre") or "").split())
    ruc = (datos.get("ruc") or "").strip() or None
    prefijo = (datos.get("prefijo_ticket") or "").strip().upper()
    dominio = (datos.get("dominio") or "").strip().lower().lstrip("@")
    titulo = " ".join((datos.get("titulo_sistema") or "").split()) or f"Mesa de Ayuda {nombre}"
    color1 = datos.get("color_primario") or "#0077B6"
    color2 = datos.get("color_secundario") or "#D6EEF8"
    if len(nombre) < 2:
        errores["nombre"] = "Escribe el nombre de la empresa."
    elif consultar("SELECT 1 FROM empresas WHERE nombre = %s", (nombre,), uno=True):
        errores["nombre"] = "Ya existe una empresa con ese nombre."
    if ruc and (not ruc.isdigit() or len(ruc) != 11):
        errores["ruc"] = "El RUC tiene 11 dígitos."
    elif ruc and consultar("SELECT 1 FROM empresas WHERE ruc = %s", (ruc,), uno=True):
        errores["ruc"] = "Ese RUC ya está registrado."
    if not prefijo.isalpha() or not 2 <= len(prefijo) <= 5:
        errores["prefijo_ticket"] = "Usa de 2 a 5 letras, por ejemplo EPS."
    elif consultar("SELECT 1 FROM empresas WHERE prefijo_ticket = %s", (prefijo,), uno=True):
        errores["prefijo_ticket"] = "Otra empresa ya usa ese prefijo."
    if not DOMINIO_RE.match(dominio):
        errores["dominio"] = "Escribe el dominio sin @, por ejemplo epsel.com.pe."
    elif consultar("SELECT 1 FROM empresa_dominios WHERE dominio = %s", (dominio,), uno=True):
        errores["dominio"] = "Ese dominio ya pertenece a otra empresa."
    if not COLOR_RE.match(color1) or not COLOR_RE.match(color2):
        errores["color_primario"] = "Los colores deben tener el formato #RRGGBB."
    admin_nombre = " ".join((datos.get("admin_nombre") or "").split())
    admin_correo = (datos.get("admin_correo") or "").strip().lower()
    admin_clave = datos.get("admin_clave") or ""
    if len(admin_nombre) < 3:
        errores["admin_nombre"] = "Escribe el nombre del administrador."
    if not correo_valido(admin_correo):
        errores["admin_correo"] = "Escribe un correo válido."
    elif "dominio" not in errores and dominio_de(admin_correo) != dominio:
        errores["admin_correo"] = f"El correo debe terminar en @{dominio}."
    elif consultar("SELECT 1 FROM users WHERE correo = %s", (admin_correo,), uno=True):
        errores["admin_correo"] = "Ese correo ya está registrado."
    error_clave = validar_clave_nueva(admin_clave)
    if error_clave:
        errores["admin_clave"] = error_clave
    areas = [a.strip()[:60] for a in (datos.get("areas") or AREAS_POR_DEFECTO).replace("\n", ",").split(",") if a.strip()]
    return {
        "nombre": nombre, "razon_social": (datos.get("razon_social") or "").strip() or None, "ruc": ruc,
        "prefijo_ticket": prefijo, "dominio": dominio, "titulo_sistema": titulo[:80],
        "color_primario": color1.upper(), "color_secundario": color2.upper(),
        "logo_url": (datos.get("logo_url") or "").strip() or None,
        "admin_nombre": admin_nombre, "admin_correo": admin_correo, "admin_clave": admin_clave,
        "areas": list(dict.fromkeys(areas)) or ["TI"],
    }, errores


def _codigo_unico(nombre):
    base = slug(nombre)
    codigo, n = base, 2
    while consultar("SELECT 1 FROM empresas WHERE codigo = %s", (codigo,), uno=True):
        codigo = f"{base[:26]}-{n}"
        n += 1
    return codigo


@empresas_bp.route("/empresas", methods=["GET", "POST"])
@roles_requeridos(ROL_SUPER)
def listado():
    errores, form = {}, {}
    if request.method == "POST":
        form = request.form
        datos, errores = _validar(request.form)
        if not errores:
            con = conexion()
            try:
                with con.cursor() as cur:
                    momento = ahora()
                    cur.execute(
                        """INSERT INTO empresas (codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema,
                                                 color_primario, color_secundario, logo_url, activo, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                        (_codigo_unico(datos["nombre"]), datos["nombre"], datos["razon_social"], datos["ruc"],
                         datos["prefijo_ticket"], datos["titulo_sistema"], datos["color_primario"],
                         datos["color_secundario"], datos["logo_url"], momento),
                    )
                    empresa_id = cur.lastrowid
                    cur.execute("INSERT INTO empresa_dominios (empresa_id, dominio) VALUES (%s, %s)",
                                (empresa_id, datos["dominio"]))
                    ids = {}
                    for nombre_area in datos["areas"]:
                        cur.execute("INSERT INTO areas (empresa_id, nombre) VALUES (%s, %s)", (empresa_id, nombre_area))
                        ids[nombre_area.upper()] = cur.lastrowid
                    area_admin = ids.get("TI") or next(iter(ids.values()))
                    cur.execute(
                        """INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol, activo, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, 'Administrador', 1, %s, %s)""",
                        (empresa_id, area_admin, datos["admin_nombre"], datos["admin_correo"],
                         hashear(datos["admin_clave"]), momento, momento),
                    )
                con.commit()
            except Exception:
                con.rollback()
                raise
            flash(f"Empresa {datos['nombre']} creada. Su administrador ya puede ingresar con {datos['admin_correo']}.", "ok")
            return redirect(url_for("empresas.listado"))
        flash("Revisa los campos marcados.", "error")
    empresas = consultar(SQL_EMPRESAS + " GROUP BY e.id ORDER BY e.nombre")
    return render_template("empresas.html", empresas=empresas, errores=errores, form=form,
                           areas_defecto=AREAS_POR_DEFECTO), (400 if errores else 200)


@empresas_bp.post("/empresas/<int:empresa_id>/administrar")
@roles_requeridos(ROL_SUPER)
def administrar(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    session["empresa_activa"] = empresa["id"]
    llenar_sesion({"id": session["usuario_id"], "nombre": session["nombre"], "correo": session["correo"],
                   "rol": ROL_SUPER, "empresa_id": None})
    flash(f"Ahora estás administrando {empresa['nombre']}.", "ok")
    return redirect(url_for("dashboard"))


@empresas_bp.post("/empresas/salir")
@roles_requeridos(ROL_SUPER)
def dejar_de_administrar():
    session["empresa_activa"] = None
    llenar_sesion({"id": session["usuario_id"], "nombre": session["nombre"], "correo": session["correo"],
                   "rol": ROL_SUPER, "empresa_id": None})
    return redirect(url_for("empresas.listado"))


@empresas_bp.post("/empresas/<int:empresa_id>/estado")
@roles_requeridos(ROL_SUPER)
def cambiar_estado(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    nuevo = 0 if empresa["activo"] else 1
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE empresas SET activo = %s WHERE id = %s", (nuevo, empresa_id))
    con.commit()
    flash(f"{empresa['nombre']} quedó {'activa' if nuevo else 'desactivada: sus usuarios ya no pueden ingresar'}.", "ok")
    return redirect(url_for("empresas.listado"))


@empresas_bp.post("/empresas/<int:empresa_id>/eliminar")
@roles_requeridos(ROL_SUPER)
def eliminar(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    if (request.form.get("confirmacion") or "").strip() != empresa["codigo"]:
        flash(f"Para eliminar escribe exactamente el código «{empresa['codigo']}».", "error")
        return redirect(url_for("empresas.listado"))
    con = conexion()
    try:
        with con.cursor() as cur:
            sub_tickets = "SELECT id FROM tickets WHERE empresa_id = %s"
            sub_users = "SELECT id FROM users WHERE empresa_id = %s"
            for sql in (
                f"DELETE FROM notificaciones WHERE referencia_ticket IN ({sub_tickets})",
                f"DELETE FROM notificaciones WHERE usuario_id IN ({sub_users})",
                f"DELETE FROM ticket_tareas WHERE ticket_id IN ({sub_tickets})",
                f"DELETE FROM ticket_historial WHERE ticket_id IN ({sub_tickets})",
                f"DELETE FROM ticket_evidencias WHERE ticket_id IN ({sub_tickets})",
                "DELETE FROM tickets WHERE empresa_id = %s",
                f"DELETE FROM tokens_revocados WHERE usuario_id IN ({sub_users})",
                "DELETE FROM users WHERE empresa_id = %s",
                "DELETE FROM areas WHERE empresa_id = %s",
                "DELETE FROM empresa_dominios WHERE empresa_id = %s",
                "DELETE FROM empresas WHERE id = %s",
            ):
                cur.execute(sql, (empresa_id,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    shutil.rmtree(os.path.join(config.UPLOAD_DIR, empresa["codigo"]), ignore_errors=True)
    if session.get("empresa_activa") == empresa_id:
        session["empresa_activa"] = None
        llenar_sesion({"id": session["usuario_id"], "nombre": session["nombre"], "correo": session["correo"],
                       "rol": ROL_SUPER, "empresa_id": None})
    flash(f"Empresa {empresa['nombre']} eliminada con sus usuarios y tickets.", "ok")
    return redirect(url_for("empresas.listado"))
