"""
Menú del perfil (arriba a la derecha):

* Mi Perfil      (/perfil)        — todos: ver sus datos y cambiar su propia contraseña.
* Configuración  (/configuracion) — Administrador (o superusuario dentro de una empresa):
                                    identidad de la empresa (título, colores, logo), sus áreas y
                                    los destinatarios y la programación del reporte (Módulo 8).
"""
from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from auth import (
    ROL_ADMIN, ROL_SUPER, clave_correcta, empresa_actual, hashear, llenar_sesion, login_requerido,
    roles_requeridos, validar_clave_nueva,
)
from correo import smtp_configurado
from db import conexion, consultar
from envios import (
    DIAS_SEMANA, destinatarios_de, enviar_reporte_empresa, periodo_de_envio, programacion_de, proximo_envio,
    semana_anterior,
)
from utils import COLOR_RE, ahora, correo_valido, entero
from vistas import V_USUARIOS_SESION

cuenta_bp = Blueprint("cuenta", __name__)

MAX_DESTINATARIOS = 20


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
    destinatarios = consultar("SELECT id, correo, semanal FROM reporte_destinatarios WHERE empresa_id = %s ORDER BY correo",
                              (empresa["id"],))
    envios = consultar(
        """SELECT origen, periodo_desde, periodo_hasta, destinatarios, estado, detalle, created_at
             FROM reporte_envios WHERE empresa_id = %s ORDER BY created_at DESC, id DESC LIMIT 10""", (empresa["id"],))
    hoy = ahora().date()
    programacion = programacion_de(empresa["id"])
    proximo = proximo_envio(empresa["id"], programacion["dia_semana"], hoy)
    return render_template("configuracion.html", e=empresa, areas=areas, dominios=dominios,
                           errores=errores, form=form, destinatarios=destinatarios, envios=envios,
                           dias_semana=DIAS_SEMANA, programacion=programacion, proximo=proximo,
                           periodo_proximo=periodo_de_envio(proximo), hoy=hoy,
                           semanales=sum(1 for d in destinatarios if d["semanal"]),
                           periodo=semana_anterior(hoy), smtp_listo=smtp_configurado()), (400 if errores else 200)


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


# ------------------------------------------------------------------ Módulo 8: reporte semanal por correo
@cuenta_bp.post("/configuracion/destinatarios")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def agregar_destinatario():
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    correo = (request.form.get("correo") or "").strip().lower()
    actuales = destinatarios_de(empresa["id"])
    if not correo_valido(correo) or len(correo) > 150:
        flash("Escribe un correo válido, por ejemplo gerencia@empresa.com.", "error")
    elif correo in actuales:
        flash("Ese correo ya está en la lista.", "error")
    elif len(actuales) >= MAX_DESTINATARIOS:
        flash(f"Se permiten hasta {MAX_DESTINATARIOS} destinatarios por empresa.", "error")
    else:
        con = conexion()
        with con.cursor() as cur:
            cur.execute("INSERT INTO reporte_destinatarios (empresa_id, correo) VALUES (%s, %s)", (empresa["id"], correo))
        con.commit()
        flash(f"{correo} recibirá el reporte semanal.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#reporte-semanal")


@cuenta_bp.post("/configuracion/destinatarios/<int:destinatario_id>/eliminar")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def eliminar_destinatario(destinatario_id):
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    con = conexion()
    with con.cursor() as cur:
        # Se filtra por empresa: nadie puede borrar los destinatarios de otra empresa
        cur.execute("DELETE FROM reporte_destinatarios WHERE id = %s AND empresa_id = %s",
                    (entero(destinatario_id), empresa["id"]))
    con.commit()
    flash("Destinatario eliminado.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#reporte-semanal")


@cuenta_bp.post("/configuracion/destinatarios/<int:destinatario_id>/semanal")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def cambiar_envio_semanal(destinatario_id):
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    semanal = 1 if request.form.get("semanal") else 0
    con = conexion()
    with con.cursor() as cur:
        # Se filtra por empresa: nadie puede cambiar los destinatarios de otra empresa
        cur.execute("UPDATE reporte_destinatarios SET semanal = %s WHERE id = %s AND empresa_id = %s",
                    (semanal, entero(destinatario_id), empresa["id"]))
    con.commit()
    flash("Destinatario actualizado.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#reporte-semanal")


@cuenta_bp.post("/configuracion/programacion")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def guardar_programacion():
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    dia = (request.form.get("dia_semana") or "").strip()
    if dia not in ("0", "1", "2", "3", "4", "5", "6"):
        flash("Elige un día de la semana válido.", "error")
        return redirect(url_for("cuenta.configuracion") + "#reporte-semanal")
    dia = int(dia)
    activo = 1 if request.form.get("activo") else 0
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO reporte_programacion (empresa_id, activo, dia_semana) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE activo = VALUES(activo), dia_semana = VALUES(dia_semana)""",
            (empresa["id"], activo, dia))
    con.commit()
    flash(f"Programación guardada: cada {DIAS_SEMANA[dia].lower()}." if activo else "Envío automático desactivado.", "ok")
    return redirect(url_for("cuenta.configuracion") + "#reporte-semanal")


def _fecha_del_formulario(campo):
    try:
        return datetime.strptime(request.form.get(campo) or "", "%Y-%m-%d").date()
    except ValueError:
        return None


@cuenta_bp.post("/configuracion/enviar-reporte")
@roles_requeridos(ROL_ADMIN, ROL_SUPER)
def enviar_reporte_ahora():
    empresa = _empresa_o_redirigir()
    if not empresa:
        return redirect(url_for("empresas.listado"))
    volver = redirect(url_for("cuenta.configuracion") + "#reporte-semanal")
    desde, hasta = _fecha_del_formulario("desde"), _fecha_del_formulario("hasta")
    if not desde or not hasta:
        flash("Elige las fechas Desde y Hasta.", "error")
        return volver
    if desde > hasta:
        flash("La fecha Desde no puede ser posterior a Hasta.", "error")
        return volver
    if hasta > ahora().date():
        flash("La fecha Hasta no puede ser futura.", "error")
        return volver
    # Solo cuentan los correos de la lista de esta empresa, aunque el formulario traiga otros ids
    elegidos = set(request.form.getlist("destinatarios"))
    filas = consultar("SELECT id, correo FROM reporte_destinatarios WHERE empresa_id = %s ORDER BY correo", (empresa["id"],))
    correos = [d["correo"] for d in filas if str(d["id"]) in elegidos]
    otro = (request.form.get("otro_correo") or "").strip().lower()
    if otro:
        if not correo_valido(otro) or len(otro) > 150:
            flash("Escribe un correo válido en «Otro correo».", "error")
            return volver
        if otro not in [d["correo"] for d in filas]:
            if len(filas) >= MAX_DESTINATARIOS:
                flash(f"Se permiten hasta {MAX_DESTINATARIOS} destinatarios por empresa.", "error")
                return volver
            con = conexion()
            with con.cursor() as cur:
                cur.execute("INSERT INTO reporte_destinatarios (empresa_id, correo, semanal) VALUES (%s, %s, 0)",
                            (empresa["id"], otro))
            con.commit()
        if otro not in correos:
            correos.append(otro)
    if not correos:
        flash("Elige al menos un destinatario o escribe un correo.", "error")
        return volver
    ok, mensaje = enviar_reporte_empresa(empresa, desde, hasta, "manual", correos, session.get("nombre", ""),
                                         g.usuario_token["id"])
    flash(mensaje, "ok" if ok else "error")
    return volver
