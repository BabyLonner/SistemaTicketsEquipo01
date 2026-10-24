"""
MÓDULO 1 — Gestión de usuarios (solo Administrador de la empresa o Superusuario).

* El administrador tiene control total de los trabajadores de SU empresa:
  registra, edita, cambia rol, restablece contraseña y activa/desactiva.
* El correo debe usar el dominio de la empresa (antes lo validaba un trigger).
* Siempre debe quedar al menos un administrador activo por empresa.
"""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from auth import empresa_filtro, es_super, hashear, roles_requeridos, validar_clave_nueva
from db import conexion, consultar
from utils import ROLES_EMPRESA, ahora, correo_valido, dominio_de, entero

usuarios_bp = Blueprint("usuarios", __name__)

SQL_LISTA = """
    SELECT u.id, u.nombre, u.correo, u.rol, u.activo, u.empresa_id, u.area_id, u.ultimo_acceso,
           e.nombre AS empresa, a.nombre AS area
      FROM users u
      LEFT JOIN empresas e ON e.id = u.empresa_id
      LEFT JOIN areas a    ON a.id = u.area_id
"""


def _empresas_visibles():
    if es_super():
        return consultar(
            """SELECT e.id, e.nombre, MIN(d.dominio) AS dominio
                 FROM empresas e LEFT JOIN empresa_dominios d ON d.empresa_id = e.id
                GROUP BY e.id, e.nombre ORDER BY e.nombre"""
        )
    return consultar(
        """SELECT e.id, e.nombre, MIN(d.dominio) AS dominio
             FROM empresas e LEFT JOIN empresa_dominios d ON d.empresa_id = e.id
            WHERE e.id = %s GROUP BY e.id, e.nombre""",
        (g.usuario["empresa_id"],),
    )


def _areas_visibles():
    if es_super():
        return consultar("SELECT id, empresa_id, nombre FROM areas WHERE activo = 1 ORDER BY nombre")
    return consultar("SELECT id, empresa_id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre",
                     (g.usuario["empresa_id"],))


def _usuario_gestionable(usuario_id):
    """Usuario de una empresa que el que está en sesión puede administrar."""
    fila = consultar(SQL_LISTA + " WHERE u.id = %s", (usuario_id,), uno=True)
    if not fila or fila["rol"] == "Superusuario":
        abort(404)
    if not es_super() and fila["empresa_id"] != g.usuario["empresa_id"]:
        abort(404)
    return fila


def _validar(datos, empresa_id, usuario_id=None, clave_obligatoria=True):
    errores = {}
    nombre = " ".join((datos.get("nombre") or "").split())
    correo = (datos.get("correo") or "").strip().lower()
    rol = datos.get("rol") or "Solicitante"
    area_id = entero(datos.get("area_id"))
    clave = datos.get("clave") or ""

    if len(nombre) < 3:
        errores["nombre"] = "Escribe el nombre completo."
    if not correo_valido(correo):
        errores["correo"] = "Escribe un correo válido."
    elif not consultar("SELECT 1 FROM empresa_dominios WHERE empresa_id = %s AND dominio = %s",
                       (empresa_id, dominio_de(correo)), uno=True):
        dominios = ", ".join("@" + d["dominio"] for d in
                             consultar("SELECT dominio FROM empresa_dominios WHERE empresa_id = %s", (empresa_id,)))
        errores["correo"] = f"El correo debe terminar en {dominios or 'el dominio de la empresa'}."
    elif consultar("SELECT 1 FROM users WHERE correo = %s AND id <> %s", (correo, usuario_id or 0), uno=True):
        errores["correo"] = "Ya existe un usuario con ese correo."
    if rol not in ROLES_EMPRESA:
        errores["rol"] = "Elige un rol válido."
    if area_id and not consultar("SELECT 1 FROM areas WHERE id = %s AND empresa_id = %s", (area_id, empresa_id), uno=True):
        errores["area_id"] = "El área no pertenece a la empresa."
    if clave or clave_obligatoria:
        error_clave = validar_clave_nueva(clave)
        if error_clave:
            errores["clave"] = error_clave
    return {"nombre": nombre, "correo": correo, "rol": rol, "area_id": area_id, "clave": clave,
            "activo": 1 if datos.get("activo") else 0}, errores


def _quedaria_sin_admin(usuario, nuevo_rol, nuevo_activo):
    """True si el cambio deja a la empresa sin administradores activos."""
    if usuario["rol"] != "Administrador" or not usuario["activo"]:
        return False
    if nuevo_rol == "Administrador" and nuevo_activo:
        return False
    otros = consultar(
        "SELECT COUNT(*) AS n FROM users WHERE empresa_id = %s AND rol = 'Administrador' AND activo = 1 AND id <> %s",
        (usuario["empresa_id"], usuario["id"]), uno=True,
    )
    return otros["n"] == 0


@usuarios_bp.route("/usuarios", methods=["GET", "POST"])
@roles_requeridos("Administrador", "Superusuario")
def listado():
    errores, form = {}, {}
    if request.method == "POST":
        form = request.form
        empresa_id = entero(request.form.get("empresa_id")) if es_super() else g.usuario["empresa_id"]
        if not empresa_id or not consultar("SELECT 1 FROM empresas WHERE id = %s", (empresa_id,), uno=True):
            errores["empresa_id"] = "Elige la empresa."
            datos = {}
        else:
            datos, errores = _validar(request.form, empresa_id)
        if not errores:
            con = conexion()
            with con.cursor() as cur:
                momento = ahora()
                cur.execute(
                    """INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol, activo, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (empresa_id, datos["area_id"], datos["nombre"], datos["correo"], hashear(datos["clave"]),
                     datos["rol"], datos["activo"], momento, momento),
                )
            con.commit()
            flash(f"Usuario {datos['nombre']} registrado. Comparte la contraseña temporal por un canal seguro.", "ok")
            return redirect(url_for("usuarios.listado"))
        flash("Revisa los campos marcados.", "error")

    q = (request.args.get("q") or "").strip()
    rol = request.args.get("rol") or ""
    estado = request.args.get("estado") or ""
    condiciones, params = ["u.rol <> 'Superusuario'"], []
    empresa_id = empresa_filtro()
    if empresa_id:
        condiciones.append("u.empresa_id = %s")
        params.append(empresa_id)
    if q:
        condiciones.append("(u.nombre LIKE %s OR u.correo LIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if rol in ROLES_EMPRESA:
        condiciones.append("u.rol = %s")
        params.append(rol)
    if estado in ("activo", "inactivo"):
        condiciones.append("u.activo = %s")
        params.append(1 if estado == "activo" else 0)
    usuarios = consultar(
        SQL_LISTA + " WHERE " + " AND ".join(condiciones)
        + " ORDER BY e.nombre, FIELD(u.rol, 'Administrador', 'Técnico', 'Solicitante'), u.nombre",
        params,
    )
    return render_template(
        "usuarios.html", usuarios=usuarios, empresas=_empresas_visibles(), areas=_areas_visibles(),
        roles=ROLES_EMPRESA, filtros={"q": q, "rol": rol, "estado": estado}, errores=errores, form=form,
    ), (400 if errores else 200)


@usuarios_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@roles_requeridos("Administrador", "Superusuario")
def editar(usuario_id):
    usuario = _usuario_gestionable(usuario_id)
    errores = {}
    if request.method == "POST":
        datos, errores = _validar(request.form, usuario["empresa_id"], usuario_id, clave_obligatoria=False)
        if usuario_id == g.usuario["id"]:
            datos["rol"], datos["activo"] = usuario["rol"], 1   # nadie se quita su propio acceso
        if not errores and _quedaria_sin_admin(usuario, datos["rol"], datos["activo"]):
            errores["rol"] = "La empresa debe conservar al menos un administrador activo."
        if not errores:
            con = conexion()
            with con.cursor() as cur:
                cur.execute(
                    """UPDATE users SET nombre = %s, correo = %s, rol = %s, area_id = %s, activo = %s, updated_at = %s
                        WHERE id = %s""",
                    (datos["nombre"], datos["correo"], datos["rol"], datos["area_id"], datos["activo"], ahora(), usuario_id),
                )
                if datos["clave"]:
                    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashear(datos["clave"]), usuario_id))
            con.commit()
            flash("Cambios guardados." + (" La contraseña fue restablecida." if datos["clave"] else ""), "ok")
            return redirect(url_for("usuarios.listado"))
        flash("Revisa los campos marcados.", "error")
    areas = consultar("SELECT id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre",
                      (usuario["empresa_id"],))
    dominio = consultar("SELECT MIN(dominio) AS d FROM empresa_dominios WHERE empresa_id = %s",
                        (usuario["empresa_id"],), uno=True)["d"]
    return render_template("usuario_editar.html", u=usuario, areas=areas, roles=ROLES_EMPRESA,
                           errores=errores, form=request.form if request.method == "POST" else usuario,
                           dominio=dominio), (400 if errores else 200)


@usuarios_bp.post("/usuarios/<int:usuario_id>/estado")
@roles_requeridos("Administrador", "Superusuario")
def cambiar_estado(usuario_id):
    usuario = _usuario_gestionable(usuario_id)
    if usuario_id == g.usuario["id"]:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("usuarios.listado"))
    nuevo = 0 if usuario["activo"] else 1
    if _quedaria_sin_admin(usuario, usuario["rol"], nuevo):
        flash("No puedes desactivar al único administrador activo de la empresa.", "error")
        return redirect(url_for("usuarios.listado"))
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET activo = %s, updated_at = %s WHERE id = %s", (nuevo, ahora(), usuario_id))
    con.commit()
    flash(f"{usuario['nombre']} quedó {'activo' if nuevo else 'inactivo'}.", "ok")
    return redirect(request.referrer or url_for("usuarios.listado"))


@usuarios_bp.get("/api/usuarios")
@roles_requeridos("Administrador", "Superusuario")
def api_listar():
    empresa_id = entero(request.args.get("empresa_id")) if es_super() else g.usuario["empresa_id"]
    sql, params = SQL_LISTA + " WHERE u.rol <> 'Superusuario'", []
    if empresa_id:
        sql += " AND u.empresa_id = %s"
        params.append(empresa_id)
    filas = consultar(sql + " ORDER BY u.nombre", params)
    for f in filas:
        f["ultimo_acceso"] = f["ultimo_acceso"].isoformat(timespec="seconds") if f["ultimo_acceso"] else None
    return jsonify(status=1, data=filas)
