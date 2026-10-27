"""
Menú del perfil (arriba a la derecha):

* Mi Perfil      (/perfil)        — todos: ver sus datos y cambiar su propia contraseña.
* Configuración  (/configuracion) — Administrador (o superusuario dentro de una empresa):
                                    identidad de la empresa (título, colores, logo) y sus áreas.
"""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from auth import (
    ROL_ADMIN, ROL_SUPER, clave_correcta, empresa_actual, hashear, llenar_sesion, login_requerido,
    roles_requeridos, validar_clave_nueva,
)
from db import conexion, consultar
from utils import COLOR_RE, ahora, entero
from vistas import V_USUARIOS_SESION

cuenta_bp = Blueprint("cuenta", __name__)


# ------------------------------------------------------------------ Mi Perfil
@cuenta_bp.route("/perfil", methods=["GET", "POST"])
@login_requerido
def perfil():
    usuario_id = g.usuario_token["id"]
    errores = {}
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        repetir = request.form.get("repetir", "")
        fila = consultar("SELECT password_hash FROM users WHERE id = %s", (usuario_id,), uno=True)
        if not clave_correcta(actual, fila["password_hash"]):
            errores["actual"] = "La contraseña actual no es correcta."
        elif nueva == actual:
            errores["nueva"] = "La nueva contraseña debe ser distinta de la actual."
        elif validar_clave_nueva(nueva):
            errores["nueva"] = validar_clave_nueva(nueva)
        elif nueva != repetir:
            errores["repetir"] = "Las contraseñas no coinciden."
        if not errores:
            con = conexion()
            with con.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
                            (hashear(nueva), ahora(), usuario_id))
            con.commit()
            flash("Tu contraseña se actualizó correctamente.", "ok")
            return redirect(url_for("cuenta.perfil"))
    usuario = consultar(f"SELECT * FROM {V_USUARIOS_SESION} AS v WHERE v.id = %s", (usuario_id,), uno=True)
    extra = consultar("SELECT created_at, ultimo_acceso FROM users WHERE id = %s", (usuario_id,), uno=True)
    resumen = None
    if usuario["rol"] != ROL_SUPER:
        resumen = consultar(
            """SELECT SUM(solicitante_id = %s) AS registrados,
                      SUM(tecnico_id = %s) AS asignados,
                      SUM(tecnico_id = %s AND estado IN ('Resuelto','Cerrado')) AS resueltos
                 FROM tickets WHERE empresa_id = %s""",
            (usuario_id, usuario_id, usuario_id, usuario["empresa_id"]), uno=True)
    return render_template("perfil.html", u=usuario, extra=extra, resumen=resumen, errores=errores), (400 if errores else 200)


# ------------------------------------------------------------------ Configuración de la empresa
def _empresa_o_redirigir():
    empresa_id = empresa_actual()
    if not empresa_id:
        flash("Elige primero la empresa que quieres administrar.", "info")
        return None
    return consultar("SELECT * FROM empresas WHERE id = %s", (empresa_id,), uno=True)


def _refrescar_identidad():
    """Vuelve a cargar en la sesión el título, color y logo de la empresa."""
    usuario = consultar(f"SELECT * FROM {V_USUARIOS_SESION} AS v WHERE v.id = %s", (g.usuario_token["id"],), uno=True)
    llenar_sesion(usuario)


@cuenta_bp.route("/configuracion", methods=["GET", "POST"])
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def configuracion():
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    errores = {}
    if request.method == "POST":
        titulo = " ".join((request.form.get("titulo_sistema") or "").split())
        color1 = (request.form.get("color_primario") or "").upper()
        color2 = (request.form.get("color_secundario") or "").upper()
        logo = (request.form.get("logo_url") or "").strip() or None
        if not 3 <= len(titulo) <= 80:
            errores["titulo_sistema"] = "El título debe tener entre 3 y 80 caracteres."
        if not COLOR_RE.match(color1) or not COLOR_RE.match(color2):
            errores["colores"] = "Los colores deben tener el formato #RRGGBB."
        if logo and not (logo.startswith("/static/") or logo.startswith("https://")):
            errores["logo_url"] = "Usa una ruta /static/... o una dirección https://"
        if not errores:
            con = conexion()
            with con.cursor() as cur:
                cur.execute("""UPDATE empresas SET titulo_sistema = %s, color_primario = %s, color_secundario = %s,
                                      logo_url = %s WHERE id = %s""",
                            (titulo, color1, color2, logo, empresa["id"]))
            con.commit()
            _refrescar_identidad()
            flash("Configuración de la empresa guardada.", "ok")
            return redirect(url_for("cuenta.configuracion"))
    areas = consultar(
        """SELECT a.id, a.nombre, a.activo,
                  (SELECT COUNT(*) FROM users u WHERE u.area_id = a.id) AS usuarios,
                  (SELECT COUNT(*) FROM tickets t WHERE t.area_id = a.id) AS tickets
             FROM areas a WHERE a.empresa_id = %s ORDER BY a.activo DESC, a.nombre""", (empresa["id"],))
    dominios = consultar("SELECT dominio FROM empresa_dominios WHERE empresa_id = %s", (empresa["id"],))
    form = request.form if request.method == "POST" else empresa
    return render_template("configuracion.html", e=empresa, areas=areas, dominios=dominios,
                           errores=errores, form=form), (400 if errores else 200)


@cuenta_bp.post("/configuracion/areas")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def agregar_area():
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    nombre = " ".join((request.form.get("nombre") or "").split())[:60]
    if len(nombre) < 2:
        flash("Escribe el nombre del área.", "error")
    elif consultar("SELECT 1 FROM areas WHERE empresa_id = %s AND nombre = %s", (empresa["id"], nombre), uno=True):
        flash("Esa área ya existe.", "error")
    else:
        con = conexion()
        with con.cursor() as cur:
            cur.execute("INSERT INTO areas (empresa_id, nombre) VALUES (%s, %s)", (empresa["id"], nombre))
        con.commit()
        flash(f"Área «{nombre}» agregada.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#areas")


@cuenta_bp.post("/configuracion/areas/<int:area_id>/estado")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def cambiar_estado_area(area_id):
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    area = consultar("SELECT id, nombre, activo FROM areas WHERE id = %s AND empresa_id = %s",
                     (entero(area_id), empresa["id"]), uno=True)
    if area:
        con = conexion()
        with con.cursor() as cur:
            cur.execute("UPDATE areas SET activo = %s WHERE id = %s", (0 if area["activo"] else 1, area["id"]))
        con.commit()
        flash(f"Área «{area['nombre']}» {'desactivada: ya no aparece en los formularios' if area['activo'] else 'activada'}.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#areas")
