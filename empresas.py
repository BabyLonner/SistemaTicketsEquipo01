"""
Gestión de empresas — SOLO SUPERUSUARIO.

* Al crear una empresa se crean también: su dominio de correo, sus áreas y
  su usuario Administrador (que desde ahí controla a sus trabajadores).
* Se puede editar su identidad visual (título y colores), activarla/desactivarla
  o eliminarla con todos sus datos (escribiendo su código para confirmar).
"""
import os
import shutil

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

import config
from auth import hashear, roles_requeridos, validar_clave_nueva
from db import conexion, consultar
from utils import COLOR_RE, DOMINIO_RE, ahora, correo_valido, dominio_de, entero, slug

empresas_bp = Blueprint("empresas", __name__)

AREAS_POR_DEFECTO = "TI, Administración, Contabilidad, Recursos Humanos, Operaciones, Logística"

SQL_EMPRESAS = """
    SELECT e.*, MIN(d.dominio) AS dominio,
           (SELECT COUNT(*) FROM users u WHERE u.empresa_id = e.id) AS total_usuarios,
           (SELECT COUNT(*) FROM tickets t WHERE t.empresa_id = e.id) AS total_tickets,
           (SELECT u.nombre FROM users u WHERE u.empresa_id = e.id AND u.rol = 'Administrador'
             ORDER BY u.id LIMIT 1) AS administrador
      FROM empresas e
      LEFT JOIN empresa_dominios d ON d.empresa_id = e.id
"""


def _empresa_o_404(empresa_id):
    fila = consultar(SQL_EMPRESAS + " WHERE e.id = %s GROUP BY e.id", (empresa_id,), uno=True)
    if not fila:
        abort(404)
    return fila


def _validar_empresa(datos, empresa_id=None):
    errores = {}
    nombre = " ".join((datos.get("nombre") or "").split())
    ruc = (datos.get("ruc") or "").strip() or None
    prefijo = (datos.get("prefijo_ticket") or "").strip().upper()
    dominio = (datos.get("dominio") or "").strip().lower().lstrip("@")
    titulo = " ".join((datos.get("titulo_sistema") or "").split()) or f"Mesa de Ayuda {nombre}"
    color1 = datos.get("color_primario") or "#3D4A8A"
    color2 = datos.get("color_secundario") or "#DCE0F5"
    otro = empresa_id or 0

    if len(nombre) < 2:
        errores["nombre"] = "Escribe el nombre de la empresa."
    elif consultar("SELECT 1 FROM empresas WHERE nombre = %s AND id <> %s", (nombre, otro), uno=True):
        errores["nombre"] = "Ya existe una empresa con ese nombre."
    if ruc and (not ruc.isdigit() or len(ruc) != 11):
        errores["ruc"] = "El RUC tiene 11 dígitos."
    elif ruc and consultar("SELECT 1 FROM empresas WHERE ruc = %s AND id <> %s", (ruc, otro), uno=True):
        errores["ruc"] = "Ese RUC ya está registrado."
    if not prefijo.isalpha() or not 2 <= len(prefijo) <= 5:
        errores["prefijo_ticket"] = "Usa de 2 a 5 letras, por ejemplo EPS."
    elif consultar("SELECT 1 FROM empresas WHERE prefijo_ticket = %s AND id <> %s", (prefijo, otro), uno=True):
        errores["prefijo_ticket"] = "Otra empresa ya usa ese prefijo."
    if not DOMINIO_RE.match(dominio):
        errores["dominio"] = "Escribe el dominio sin @, por ejemplo epsel.com.pe."
    elif consultar("SELECT 1 FROM empresa_dominios WHERE dominio = %s AND empresa_id <> %s", (dominio, otro), uno=True):
        errores["dominio"] = "Ese dominio ya pertenece a otra empresa."
    if not COLOR_RE.match(color1) or not COLOR_RE.match(color2):
        errores["color_primario"] = "Los colores deben tener el formato #RRGGBB."
    return {
        "nombre": nombre, "razon_social": (datos.get("razon_social") or "").strip() or None, "ruc": ruc,
        "prefijo_ticket": prefijo, "dominio": dominio, "titulo_sistema": titulo[:80],
        "color_primario": color1.upper(), "color_secundario": color2.upper(),
    }, errores


def _codigo_unico(nombre):
    base = slug(nombre)
    codigo, n = base, 2
    while consultar("SELECT 1 FROM empresas WHERE codigo = %s", (codigo,), uno=True):
        codigo = f"{base[:26]}-{n}"
        n += 1
    return codigo


@empresas_bp.route("/empresas", methods=["GET", "POST"])
@roles_requeridos("Superusuario")
def listado():
    errores, form = {}, {}
    if request.method == "POST":
        form = request.form
        datos, errores = _validar_empresa(request.form)
        admin_nombre = " ".join((request.form.get("admin_nombre") or "").split())
        admin_correo = (request.form.get("admin_correo") or "").strip().lower()
        admin_clave = request.form.get("admin_clave") or ""
        areas = [a.strip() for a in (request.form.get("areas") or AREAS_POR_DEFECTO).replace("\n", ",").split(",") if a.strip()]
        if len(admin_nombre) < 3:
            errores["admin_nombre"] = "Escribe el nombre del administrador."
        if not correo_valido(admin_correo):
            errores["admin_correo"] = "Escribe un correo válido."
        elif "dominio" not in errores and dominio_de(admin_correo) != datos["dominio"]:
            errores["admin_correo"] = f"El correo debe terminar en @{datos['dominio']}."
        elif consultar("SELECT 1 FROM users WHERE correo = %s", (admin_correo,), uno=True):
            errores["admin_correo"] = "Ese correo ya está registrado."
        error_clave = validar_clave_nueva(admin_clave)
        if error_clave:
            errores["admin_clave"] = error_clave
        if not errores:
            con = conexion()
            try:
                with con.cursor() as cur:
                    momento = ahora()
                    cur.execute(
                        """INSERT INTO empresas (codigo, nombre, razon_social, ruc, prefijo_ticket, titulo_sistema,
                                                 color_primario, color_secundario, activo, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                        (_codigo_unico(datos["nombre"]), datos["nombre"], datos["razon_social"], datos["ruc"],
                         datos["prefijo_ticket"], datos["titulo_sistema"], datos["color_primario"],
                         datos["color_secundario"], momento),
                    )
                    empresa_id = cur.lastrowid
                    cur.execute("INSERT INTO empresa_dominios (empresa_id, dominio) VALUES (%s, %s)",
                                (empresa_id, datos["dominio"]))
                    ids_areas = {}
                    for nombre_area in dict.fromkeys(areas):
                        cur.execute("INSERT INTO areas (empresa_id, nombre) VALUES (%s, %s)", (empresa_id, nombre_area[:60]))
                        ids_areas[nombre_area.upper()] = cur.lastrowid
                    # El administrador queda en el área TI (o en la primera si no hay TI)
                    area_admin = ids_areas.get("TI") or next(iter(ids_areas.values()), None)
                    cur.execute(
                        """INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol, activo, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, 'Administrador', 1, %s, %s)""",
                        (empresa_id, area_admin, admin_nombre, admin_correo, hashear(admin_clave), momento, momento),
                    )
                con.commit()
            except Exception:
                con.rollback()
                raise
            flash(f"Empresa {datos['nombre']} creada. Su administrador ya puede ingresar con {admin_correo}.", "ok")
            return redirect(url_for("empresas.listado"))
        flash("Revisa los campos marcados.", "error")
    empresas = consultar(SQL_EMPRESAS + " GROUP BY e.id ORDER BY e.nombre")
    return render_template("empresas.html", empresas=empresas, errores=errores, form=form,
                           areas_defecto=AREAS_POR_DEFECTO), (400 if errores else 200)


@empresas_bp.route("/empresas/<int:empresa_id>/editar", methods=["GET", "POST"])
@roles_requeridos("Superusuario")
def editar(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    errores = {}
    if request.method == "POST":
        datos, errores = _validar_empresa(request.form, empresa_id)
        if not errores:
            con = conexion()
            try:
                with con.cursor() as cur:
                    cur.execute(
                        """UPDATE empresas SET nombre = %s, razon_social = %s, ruc = %s, prefijo_ticket = %s,
                                  titulo_sistema = %s, color_primario = %s, color_secundario = %s WHERE id = %s""",
                        (datos["nombre"], datos["razon_social"], datos["ruc"], datos["prefijo_ticket"],
                         datos["titulo_sistema"], datos["color_primario"], datos["color_secundario"], empresa_id),
                    )
                    if datos["dominio"] != empresa["dominio"]:
                        # Cambia el dominio y el correo de todos sus usuarios (nombre.apellido@nuevo)
                        cur.execute("DELETE FROM empresa_dominios WHERE empresa_id = %s", (empresa_id,))
                        cur.execute("INSERT INTO empresa_dominios (empresa_id, dominio) VALUES (%s, %s)",
                                    (empresa_id, datos["dominio"]))
                        cur.execute(
                            "UPDATE users SET correo = CONCAT(SUBSTRING_INDEX(correo, '@', 1), '@', %s) WHERE empresa_id = %s",
                            (datos["dominio"], empresa_id),
                        )
                con.commit()
            except Exception:
                con.rollback()
                raise
            flash("Empresa actualizada.", "ok")
            return redirect(url_for("empresas.listado"))
        flash("Revisa los campos marcados.", "error")
    areas = consultar("SELECT id, nombre, activo FROM areas WHERE empresa_id = %s ORDER BY nombre", (empresa_id,))
    return render_template("empresa_editar.html", e=empresa, areas=areas, errores=errores,
                           form=request.form if request.method == "POST" else empresa), (400 if errores else 200)


@empresas_bp.post("/empresas/<int:empresa_id>/areas")
@roles_requeridos("Superusuario")
def agregar_area(empresa_id):
    _empresa_o_404(empresa_id)
    nombre = " ".join((request.form.get("nombre") or "").split())[:60]
    if len(nombre) < 2:
        flash("Escribe el nombre del área.", "error")
    elif consultar("SELECT 1 FROM areas WHERE empresa_id = %s AND nombre = %s", (empresa_id, nombre), uno=True):
        flash("Esa área ya existe.", "error")
    else:
        con = conexion()
        with con.cursor() as cur:
            cur.execute("INSERT INTO areas (empresa_id, nombre) VALUES (%s, %s)", (empresa_id, nombre))
        con.commit()
        flash(f"Área {nombre} agregada.", "ok")
    return redirect(url_for("empresas.editar", empresa_id=empresa_id))


@empresas_bp.post("/empresas/<int:empresa_id>/estado")
@roles_requeridos("Superusuario")
def cambiar_estado(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    nuevo = 0 if empresa["activo"] else 1
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE empresas SET activo = %s WHERE id = %s", (nuevo, empresa_id))
    con.commit()
    flash(f"{empresa['nombre']} quedó {'activa' if nuevo else 'desactivada: sus usuarios ya no pueden ingresar'}.", "ok")
    return redirect(url_for("empresas.listado"))


def eliminar_empresa(empresa):
    """Borra la empresa y TODO lo suyo en una transacción (sin depender de ON DELETE CASCADE)."""
    eid = empresa["id"]
    con = conexion()
    try:
        with con.cursor() as cur:
            sub_tickets = "SELECT id FROM tickets WHERE empresa_id = %s"
            sub_users = "SELECT id FROM users WHERE empresa_id = %s"
            pasos = [
                f"DELETE FROM notificaciones WHERE referencia_ticket IN ({sub_tickets})",
                f"DELETE FROM notificaciones WHERE usuario_id IN ({sub_users})",
                f"DELETE FROM ticket_historial WHERE ticket_id IN ({sub_tickets})",
                f"DELETE FROM ticket_evidencias WHERE ticket_id IN ({sub_tickets})",
                "DELETE FROM tickets WHERE empresa_id = %s",
                f"DELETE FROM tokens_revocados WHERE usuario_id IN ({sub_users})",
                "DELETE FROM users WHERE empresa_id = %s",
                "DELETE FROM areas WHERE empresa_id = %s",
                "DELETE FROM empresa_dominios WHERE empresa_id = %s",
                "DELETE FROM empresas WHERE id = %s",
            ]
            for sql in pasos:
                cur.execute(sql, (eid,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    shutil.rmtree(os.path.join(config.UPLOAD_DIR, empresa["codigo"]), ignore_errors=True)


@empresas_bp.post("/empresas/<int:empresa_id>/eliminar")
@roles_requeridos("Superusuario")
def eliminar(empresa_id):
    empresa = _empresa_o_404(empresa_id)
    if (request.form.get("confirmacion") or "").strip() != empresa["codigo"]:
        flash(f"Para eliminar escribe exactamente el código «{empresa['codigo']}».", "error")
        return redirect(url_for("empresas.editar", empresa_id=empresa_id) + "#zona-peligro")
    eliminar_empresa(empresa)
    flash(f"Empresa {empresa['nombre']} eliminada con sus usuarios y tickets.", "ok")
    return redirect(url_for("empresas.listado"))


@empresas_bp.get("/api/empresas")
@roles_requeridos("Superusuario")
def api_listar():
    filas = consultar(SQL_EMPRESAS + " GROUP BY e.id ORDER BY e.nombre")
    for f in filas:
        f["created_at"] = f["created_at"].isoformat(timespec="seconds")
    return jsonify(status=1, data=filas)
