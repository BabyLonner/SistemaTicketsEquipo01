"""
MESA DE AYUDA TI — Sistema de gestión de tickets para las 6 empresas del grupo.
Local:  python run.py     |     PythonAnywhere: lo importa el archivo WSGI.

Módulos
  1  auth.py, usuarios.py, empresas.py   JWT, roles, usuarios y empresas (superusuario)
  2-4 tickets.py                         Tickets + fotos, asignación/estados/historial, SLA
  5  (este archivo)                      Notificaciones internas (campana)
  6  (este archivo) + reportes.py        Dashboard, SLA, reportes y exportación Excel/PDF
  8  verificacion.py                     Verificación del PDF con QR + hash SHA-256 (página pública)
     api_postman.py                      Rutas de la colección de Postman (piden JWT)
"""
import config
from flask import Flask, abort, flash, g, jsonify, make_response, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound

from api_postman import api_postman_bp
from avisos_whatsapp import avisos_bp  # MÓDULO 4: avisos por WhatsApp (Vonage)
from equipos import equipos_bp         # MÓDULO 3 (avance 2): etiquetas QR por equipo
from cuenta import cuenta_bp
from auth import (
    ROL_ADMIN, ROL_SOLICITANTE, ROL_SUPER, ROL_TECNICO, autenticar, crear_token, empresa_actual, es_super,
    llenar_sesion, login_requerido, registrar_acceso, revocar_token_actual, roles_requeridos, validar_peticion,
)
from db import cerrar_conexion, conexion, consultar
from empresas import empresas_bp
from reportes import reportes_bp
from tickets import tickets_bp
from usuarios import usuarios_bp
from utils import ordenar_por_urgencia
from verificacion import verificacion_bp
from facial import facial_bp            # MÓDULO 1: login con reconocimiento facial
from vistas import V_TICKETS, aplicar_sla_lista

app = Flask(__name__)
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.json.ensure_ascii = False
app.json.sort_keys = False

for bp in (tickets_bp, usuarios_bp, empresas_bp, reportes_bp, cuenta_bp, api_postman_bp, verificacion_bp,
           avisos_bp, equipos_bp, facial_bp):
    app.register_blueprint(bp)

app.before_request(validar_peticion)       # MÓDULO 1: el JWT se valida en CADA petición
app.teardown_appcontext(cerrar_conexion)

# Quién puede abrir cada pantalla (el menú lo oculta, pero aquí se impide de verdad)
TODOS = (ROL_SUPER, ROL_ADMIN, ROL_TECNICO, ROL_SOLICITANTE)
PERMISOS_PAGINAS = {
    "tickets": TODOS,
    "detalle_ticket": TODOS,
    "notificaciones": TODOS,
    "mis_tickets": (ROL_ADMIN, ROL_TECNICO, ROL_SOLICITANTE),
    "nuevo_ticket": (ROL_ADMIN, ROL_TECNICO, ROL_SOLICITANTE),
    "dashboard": (ROL_SUPER, ROL_ADMIN, ROL_TECNICO),
    "reportes": (ROL_SUPER, ROL_ADMIN, ROL_TECNICO),
    "sla": (ROL_SUPER, ROL_ADMIN),
    "asignacion": (ROL_SUPER, ROL_ADMIN),
    "usuarios": (ROL_SUPER, ROL_ADMIN),
    "equipos": (ROL_SUPER, ROL_ADMIN, ROL_TECNICO),   # MÓDULO 3 (avance 2)
}
# Pantallas que trabajan dentro de una empresa: el superusuario primero debe elegirla
NECESITAN_EMPRESA = {"tickets", "detalle_ticket", "dashboard", "reportes", "sla", "asignacion", "usuarios", "equipos"}


def _mezclar(color, otro, proporcion):
    """Mezcla dos colores #RRGGBB (proporcion 0 = color, 1 = otro)."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(otro[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * proporcion):02X}" for x, y in zip(a, b))


def paleta_empresa():
    """Identidad visual de la empresa activa (colores de la tabla empresas).
    Sin empresa (superusuario o login) se usan los colores originales del sistema."""
    primario = session.get("empresa_color")
    if not primario or len(primario) != 7:
        return None
    secundario = session.get("empresa_color2") or _mezclar(primario, "#FFFFFF", 0.85)
    return {
        "primario": primario,
        "oscuro": _mezclar(primario, "#000000", 0.35),     # cabecera
        "profundo": _mezclar(primario, "#000000", 0.5),
        "medio": _mezclar(primario, "#FFFFFF", 0.15),
        "claro": _mezclar(primario, "#FFFFFF", 0.9),        # fondos suaves
        "lienzo": _mezclar(secundario, "#FFFFFF", 0.6),     # fondo de la página
        "secundario": secundario,
    }


@app.context_processor
def datos_globales():
    return {"version": config.VERSION, "es_superusuario": es_super(), "paleta": paleta_empresa()}


def pagina_permitida(pagina):
    """Devuelve una respuesta de error/redirección si el usuario no puede ver la página."""
    if not g.get("usuario_token"):
        return redirect(url_for("inicio"))
    roles = PERMISOS_PAGINAS.get(pagina)
    if roles is None:
        abort(404)
    if g.usuario_token["rol"] not in roles:
        return render_template("error.html", codigo=403,
                               mensaje="Tu rol no tiene permiso para abrir esta pantalla."), 403
    if es_super() and pagina in NECESITAN_EMPRESA and not empresa_actual():
        flash("Elige la empresa que quieres administrar.", "info")
        return redirect(url_for("empresas.listado"))
    return None


# =====================================================================
#  MÓDULO 1: identidad de la empresa, login y logout
# =====================================================================
@app.route("/api/identidad-empresa", methods=["GET"])
def api_identidad_empresa():
    correo = (request.args.get("correo") or "").strip().lower()
    dominio = correo.split("@", 1)[1].strip() if "@" in correo else ""
    if not dominio:
        return jsonify({"encontrado": False})
    empresa = consultar(
        """SELECT e.id, e.codigo, e.nombre, e.titulo_sistema, e.color_primario, e.color_secundario, e.logo_url
             FROM empresa_dominios d JOIN empresas e ON e.id = d.empresa_id
            WHERE d.dominio = %s AND e.activo = 1 LIMIT 1""",
        (dominio,), uno=True,
    )
    return jsonify({"encontrado": bool(empresa), "empresa": empresa} if empresa else {"encontrado": False})


def _destino_inicial(rol):
    return url_for("empresas.listado") if rol == ROL_SUPER else url_for("pantalla", pagina="tickets")


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        usuario, error = autenticar(request.form.get("correo"), request.form.get("clave", ""))
        if error:
            flash(error, "error")
            return redirect(url_for("inicio"))
        recordar = request.form.get("recordar") in ("1", "on", "true")
        token, duracion = crear_token(usuario, recordar)
        registrar_acceso(usuario["id"])
        session.clear()
        llenar_sesion(usuario)
        respuesta = make_response(redirect(_destino_inicial(usuario["rol"])))
        respuesta.set_cookie(
            config.COOKIE_TOKEN, token,
            max_age=int(duracion.total_seconds()) if recordar else None,
            httponly=True, samesite="Lax", secure=request.is_secure,
        )
        return respuesta
    if g.get("usuario_token"):
        return redirect(_destino_inicial(g.usuario_token["rol"]))
    return render_template("index.html")


@app.route("/cerrar-sesion")
def cerrar_sesion():
    revocar_token_actual()            # el jti pasa a tokens_revocados: el token ya no sirve
    session.clear()
    respuesta = make_response(redirect(url_for("inicio")))
    respuesta.delete_cookie(config.COOKIE_TOKEN)
    return respuesta


@app.post("/api/login")
def api_login():
    """Postman: {"correo": "...", "password": "..."} -> token JWT (Authorization: Bearer)."""
    datos = request.get_json(silent=True) or request.form
    usuario, error = autenticar(datos.get("correo"), datos.get("password") or datos.get("clave", ""))
    if error:
        return jsonify(status=-1, message=error), 401
    token, duracion = crear_token(usuario, bool(datos.get("recordar")))
    registrar_acceso(usuario["id"])
    return jsonify(status=1, message="Inicio de sesión correcto", data={
        "token": token, "tipo": "Bearer", "expira_en_segundos": int(duracion.total_seconds()),
        "usuario": {"id": usuario["id"], "nombre": usuario["nombre"], "correo": usuario["correo"],
                    "rol": usuario["rol"], "empresa_id": usuario["empresa_id"], "empresa": usuario["empresa"]},
    })


@app.post("/api/logout")
@login_requerido
def api_logout():
    revocar_token_actual()
    return jsonify(status=1, message="Token invalidado")


# =====================================================================
#  MÓDULO 5: API REST DE NOTIFICACIONES INTERNAS
# =====================================================================
@app.route("/api/notificaciones", methods=["GET"])
@login_requerido
def api_listar_notificaciones():
    usuario_id = g.usuario_token["id"]
    fila = consultar("SELECT COUNT(*) AS no_leidas FROM notificaciones WHERE usuario_id = %s AND leido = 0",
                     (usuario_id,), uno=True)
    notificaciones = consultar(
        """SELECT n.id, n.tipo, n.referencia_ticket, n.titulo, n.mensaje, n.leido,
                  DATE_FORMAT(n.created_at, '%%d/%%m/%%Y %%H:%%i') AS fecha_formateada,
                  TIMESTAMPDIFF(MINUTE, n.created_at, NOW()) AS hace_minutos
             FROM notificaciones n
            WHERE n.usuario_id = %s
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT 50""",
        (usuario_id,),
    )
    return jsonify({"ok": True, "no_leidas": fila["no_leidas"], "notificaciones": notificaciones})


@app.route("/api/notificaciones/<int:notif_id>/leer", methods=["POST", "PUT"])
@login_requerido
def api_marcar_notificacion_leida(notif_id):
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE id = %s AND usuario_id = %s",
                    (notif_id, g.usuario_token["id"]))
    con.commit()
    return jsonify({"ok": True})


@app.route("/api/notificaciones/leer-todas", methods=["POST", "PUT"])
@login_requerido
def api_marcar_todas_leidas():
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE usuario_id = %s AND leido = 0",
                    (g.usuario_token["id"],))
        total = cur.rowcount
    con.commit()
    return jsonify({"ok": True, "marcadas": total})


# =====================================================================
#  Indicadores "vs. mes anterior" de las tarjetas (datos reales)
#  Compara lo REGISTRADO este mes contra lo registrado el mes anterior.
# =====================================================================
def _comparar(sql, params):
    """sql debe devolver columnas mes_actual_<x> y mes_anterior_<x>."""
    fila = consultar(sql, params, uno=True) or {}
    datos = {}
    for clave, valor in fila.items():
        if not clave.startswith("act_"):
            continue
        nombre = clave[4:]
        actual, anterior = int(valor or 0), int(fila.get("ant_" + nombre) or 0)
        pct = round(100 * (actual - anterior) / anterior) if anterior else None
        datos[nombre] = {"actual": actual, "anterior": anterior, "variacion": pct}
    return datos


def _columnas_mes(expresiones, campo_fecha):
    """Para cada métrica arma SUM(...) del mes actual y del anterior."""
    actual = f"{campo_fecha} >= DATE_FORMAT(NOW(), '%%Y-%%m-01')"
    anterior = (f"{campo_fecha} >= DATE_FORMAT(NOW() - INTERVAL 1 MONTH, '%%Y-%%m-01') "
                f"AND {campo_fecha} < DATE_FORMAT(NOW(), '%%Y-%%m-01')")
    partes = []
    for nombre, condicion in expresiones.items():
        partes.append(f"COALESCE(SUM(({actual}) AND ({condicion})), 0) AS act_{nombre}")
        partes.append(f"COALESCE(SUM(({anterior}) AND ({condicion})), 0) AS ant_{nombre}")
    return ", ".join(partes)


@app.get("/api/tendencias")
@login_requerido
def api_tendencias():
    usuario = g.usuario_token
    empresa_id = empresa_actual()
    resultado = {}
    metricas_tickets = {
        "total": "1", "abiertos": "estado = 'Abierto'", "en_proceso": "estado = 'En proceso'",
        "resueltos": "estado = 'Resuelto'", "cerrados": "estado = 'Cerrado'",
        "vencidos": "estado NOT IN ('Resuelto','Cerrado') AND fecha_limite < NOW()",
        "pendientes": "estado = 'Abierto' OR (estado NOT IN ('Resuelto','Cerrado') AND fecha_limite < NOW())",
    }
    if empresa_id:
        resultado["tickets"] = _comparar(
            f"SELECT {_columnas_mes(metricas_tickets, 'created_at')} FROM tickets WHERE empresa_id = %s", (empresa_id,))
        if usuario["rol"] in (ROL_ADMIN, ROL_SUPER):
            resultado["usuarios"] = _comparar(
                f"""SELECT {_columnas_mes({"total": "1", "administradores": "rol = 'Administrador'",
                                           "tecnicos": "rol = 'Técnico'", "solicitantes": "rol = 'Solicitante'"}, 'created_at')}
                      FROM users WHERE empresa_id = %s""", (empresa_id,))
    if usuario["rol"] != ROL_SUPER:
        resultado["mios"] = _comparar(
            f"SELECT {_columnas_mes(metricas_tickets, 'created_at')} FROM tickets WHERE solicitante_id = %s OR tecnico_id = %s",
            (usuario["id"], usuario["id"]))
    resultado["notificaciones"] = _comparar(
        f"""SELECT {_columnas_mes({"total": "1", "no_leidas": "leido = 0",
                                   "tickets": "tipo IN ('NUEVO_TICKET','ASIGNACION','CAMBIO_ESTADO','COMENTARIO')",
                                   "sistema": "tipo = 'SLA'"}, 'created_at')}
              FROM notificaciones WHERE usuario_id = %s""", (usuario["id"],))
    return jsonify(resultado)


# =====================================================================
#  MÓDULO 6: DASHBOARD, SLA Y REPORTES
# =====================================================================
def obtener_datos_dashboard(empresa_id):
    kpis = consultar(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,
                  COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,
                  COALESCE(SUM(estado NOT IN ('Resuelto','Cerrado') AND fecha_limite < NOW()), 0) AS vencidos
             FROM tickets WHERE empresa_id = %s""", (empresa_id,), uno=True)
    estados = consultar("SELECT estado, COUNT(*) AS total FROM tickets WHERE empresa_id = %s GROUP BY estado",
                        (empresa_id,))
    prioridades = consultar(
        """SELECT p.nombre AS prioridad, COUNT(*) AS total
             FROM tickets t JOIN prioridades p ON p.id = t.prioridad_id
            WHERE t.empresa_id = %s GROUP BY p.id, p.nombre, p.nivel ORDER BY p.nivel DESC""", (empresa_id,))
    tecnicos = consultar(
        """SELECT u.nombre AS tecnico, COUNT(t.id) AS total
             FROM tickets t JOIN users u ON u.id = t.tecnico_id
            WHERE t.empresa_id = %s GROUP BY u.id, u.nombre ORDER BY total DESC LIMIT 8""", (empresa_id,))
    categorias = consultar(
        """SELECT c.nombre AS categoria, COUNT(*) AS total
             FROM tickets t JOIN categorias c ON c.id = t.categoria_id
            WHERE t.empresa_id = %s GROUP BY c.id, c.nombre ORDER BY total DESC""", (empresa_id,))
    recientes = consultar(
        """SELECT t.id, t.asunto, t.estado, t.created_at, p.nombre AS prioridad, u.nombre AS tecnico
             FROM tickets t JOIN prioridades p ON p.id = t.prioridad_id
             LEFT JOIN users u ON u.id = t.tecnico_id
            WHERE t.empresa_id = %s ORDER BY t.created_at DESC LIMIT 5""", (empresa_id,))
    return {"kpis": kpis, "estados": estados, "prioridades": prioridades, "tecnicos": tecnicos,
            "categorias": categorias, "recientes": recientes}


@app.route("/dashboard")
def dashboard():
    error = pagina_permitida("dashboard")
    if error:
        return error
    return render_template("dashboard.html", datos=obtener_datos_dashboard(empresa_actual()))


@app.route("/sla")
def sla():
    error = pagina_permitida("sla")
    if error:
        return error
    tickets = consultar(f"SELECT * FROM {V_TICKETS} AS v WHERE v.empresa_id = %s", (empresa_actual(),))
    tickets = ordenar_por_urgencia(aplicar_sla_lista(tickets))      # semáforo calculado en Python
    prioridades = consultar("SELECT id, nombre, sla_horas FROM prioridades ORDER BY nivel DESC")
    return render_template("sla.html", tickets=tickets, prioridades=prioridades)


@app.route("/reportes")
def reportes():
    error = pagina_permitida("reportes")
    if error:
        return error
    empresa_id = empresa_actual()
    tickets = consultar(
        """SELECT t.id, t.numero, CONCAT(e.prefijo_ticket, '-', LPAD(t.numero, 4, '0')) AS codigo,
                  t.asunto, t.descripcion, t.estado, t.created_at, t.updated_at, t.fecha_limite,
                  t.fecha_resolucion, s.nombre AS solicitante,
                  COALESCE(a.nombre, 'Sin área') AS area, COALESCE(c.nombre, 'Sin categoría') AS categoria,
                  COALESCE(p.nombre, 'Sin prioridad') AS prioridad, COALESCE(tec.nombre, 'Sin asignar') AS tecnico
             FROM tickets t
             JOIN empresas e ON e.id = t.empresa_id
             LEFT JOIN users s ON s.id = t.solicitante_id
             LEFT JOIN areas a ON a.id = t.area_id
             LEFT JOIN categorias c ON c.id = t.categoria_id
             LEFT JOIN prioridades p ON p.id = t.prioridad_id
             LEFT JOIN users tec ON tec.id = t.tecnico_id
            WHERE t.empresa_id = %s
            ORDER BY t.created_at DESC, t.id DESC""", (empresa_id,))
    areas = [r["nombre"] for r in consultar(
        "SELECT DISTINCT nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre", (empresa_id,))]
    categorias = [r["nombre"] for r in consultar("SELECT nombre FROM categorias WHERE activo = 1 ORDER BY nombre")]
    prioridades = [r["nombre"] for r in consultar("SELECT nombre FROM prioridades ORDER BY nivel DESC")]
    tecnicos = [r["nombre"] for r in consultar(
        "SELECT nombre FROM users WHERE empresa_id = %s AND rol = 'Técnico' ORDER BY nombre", (empresa_id,))]
    return render_template("reportes.html", tickets=tickets, areas=areas, categorias=categorias,
                           prioridades=prioridades, tecnicos=tecnicos)


# Acepta la ruta con o sin .html, pero SOLO las pantallas de la lista y según el rol
@app.route("/<pagina>")
@app.route("/<pagina>.html")
def pantalla(pagina):
    if pagina == "index":
        return redirect(url_for("cerrar_sesion"))
    if pagina in ("dashboard", "reportes", "sla"):
        return redirect(url_for(pagina))
    error = pagina_permitida(pagina)
    if error:
        return error
    try:
        return render_template(f"{pagina}.html")
    except TemplateNotFound:
        abort(404)


@app.get("/salud")
def salud():
    """Comprueba que la app y la base de datos respondan (útil en PythonAnywhere)."""
    try:
        consultar("SELECT 1 AS ok", uno=True)
        return jsonify(ok=True, base_de_datos="conectada", version=config.VERSION)
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, error=str(e)), 500


def _error(codigo, mensaje):
    if request.path.startswith("/api"):
        return jsonify(status=-1, ok=False, error=mensaje, message=mensaje), codigo
    return render_template("error.html", codigo=codigo, mensaje=mensaje), codigo


@app.errorhandler(404)
def no_encontrado(_e):
    return _error(404, "La página o el registro que buscas no existe, o no tienes acceso a él.")


@app.errorhandler(500)
def error_interno(_e):
    return _error(500, "Ocurrió un error inesperado. Inténtalo de nuevo en un momento.")


if __name__ == "__main__":
    app.run(debug=True)
