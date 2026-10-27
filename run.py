import os
import unicodedata
import uuid
from functools import wraps

import bcrypt
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from jinja2 import TemplateNotFound

from db import obtener_conexion
from tickets import tickets_bp

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave-local-solo-desarrollo")
app.register_blueprint(tickets_bp)


def login_requerido(func):
    """Restringe el acceso a rutas que requieren una sesión iniciada."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("inicio"))
        return func(*args, **kwargs)

    return wrapper


# Colores distintivos por empresa
COLORES_EMPRESAS = {
    "epsel": "#1E88D2",
    "grupo m&m": "#24273D",
    "robotic air systems": "#2672C7",
    "angel divino": "#5B1879",
    "agrofutura": "#4C8B41",
    "atlantica": "#1336BF",
}


def normalizar_nombre_empresa(nombre):
    nombre = unicodedata.normalize("NFD", nombre or "")
    nombre = "".join(c for c in nombre if unicodedata.category(c) != "Mn")
    return " ".join(nombre.casefold().split())


def obtener_identidad_empresa(empresa_id):
    """Devuelve el nombre, color y logo real de la empresa del usuario conectado."""
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT nombre, color_primario, logo_url FROM empresas WHERE id = %s LIMIT 1",
                (empresa_id,),
            )
            empresa = cursor.fetchone()

        if empresa:
            return {
                "nombre": empresa["nombre"],
                "color": empresa["color_primario"],
                "logo": empresa["logo_url"],
            }
        return {"nombre": "Empresa", "color": "#2672C7", "logo": ""}
    finally:
        conexion.close()


@app.route("/api/identidad-empresa", methods=["GET"])
def api_identidad_empresa():
    correo = (request.args.get("correo") or "").strip().lower()
    if "@" not in correo:
        return jsonify({"encontrado": False})

    dominio = correo.split("@", 1)[1].strip()
    if not dominio:
        return jsonify({"encontrado": False})

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.id, e.codigo, e.nombre, e.titulo_sistema,
                       e.color_primario, e.color_secundario, e.logo_url
                FROM empresa_dominios d
                JOIN empresas e ON e.id = d.empresa_id
                WHERE d.dominio = %s AND e.activo = 1
                LIMIT 1
                """,
                (dominio,),
            )
            empresa = cursor.fetchone()

        if not empresa:
            return jsonify({"encontrado": False})

        return jsonify({"encontrado": True, "empresa": empresa})
    finally:
        conexion.close()


@app.route("/", methods=["GET", "POST"])
def inicio():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")

        if not correo or not clave:
            flash("Ingresa tu correo y contraseña.", "error")
            return redirect(url_for("inicio"))

        conexion = obtener_conexion()
        try:
            with conexion.cursor() as cursor:
                # Se utiliza v_usuarios_sesion para traer todos los colores y logos
                cursor.execute(
                    """
                    SELECT id, nombre, correo, password_hash, rol, activo,
                           empresa_id, empresa, titulo_sistema,
                           color_primario, color_secundario, logo_url, empresa_activa
                    FROM v_usuarios_sesion
                    WHERE correo = %s
                    LIMIT 1
                    """,
                    (correo,),
                )
                usuario = cursor.fetchone()

            if not usuario or not usuario["activo"] or not usuario["empresa_activa"]:
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))

            if not bcrypt.checkpw(
                clave.encode("utf-8"), usuario["password_hash"].encode("utf-8")
            ):
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))

            session.clear()
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["nombre"] = usuario["nombre"]
            session["correo"] = usuario["correo"]
            session["rol"] = usuario["rol"]
            session["empresa_nombre"] = usuario["empresa"]
            session["empresa_titulo"] = usuario["titulo_sistema"]
            session["empresa_logo"] = usuario["logo_url"]
            session["empresa_color"] = usuario["color_primario"]

            with conexion.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET ultimo_acceso = NOW() WHERE id = %s",
                    (usuario["id"],),
                )
            conexion.commit()

            # Redirige temporalmente a tickets en lugar de dashboard,
            # ya que el rol "Solicitante" no tiene acceso al dashboard.
            return redirect(url_for("pantalla", pagina="tickets"))

        except Exception:
            app.logger.exception("Error durante el inicio de sesión")
            flash("No se pudo completar el acceso. Inténtalo nuevamente.", "error")
            return redirect(url_for("inicio"))
        finally:
            conexion.close()

    if session.get("usuario_id"):
        return redirect(url_for("pantalla", pagina="tickets"))

    return render_template("index.html")


@app.route("/cerrar-sesion")
def cerrar_sesion():

    session.clear()

    return redirect(url_for("inicio"))


# =====================================================================*

# MÓDULO 5: API REST DE NOTIFICACIONES INTERNAS*

# =====================================================================*


@app.route("/api/notificaciones", methods=["GET"])
def api_listar_notificaciones():

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            # *&#x20;1. Cantidad de notificaciones no leídas para el globo rojo (badge)*

            cursor.execute(
                """

                SELECT COUNT(*) AS no_leidas

                FROM notificaciones

                WHERE usuario_id = %s AND leido = 0

                """,
                (usuario_id,),
            )

            fila_count = cursor.fetchone()

            no_leidas = fila_count["no_leidas"] if fila_count else 0

            # *&#x20;2. Últimas 20 notificaciones del usuario con código de ticket si aplica*

            cursor.execute(
                """

                SELECT n.id,

                       n.tipo,

                       n.referencia_ticket,

                       n.titulo,

                       n.mensaje,

                       n.leido,

                       DATE_FORMAT(n.created_at, '%%d/%%m/%%Y %%H:%%i') AS fecha_formateada,

                       TIMESTAMPDIFF(MINUTE, n.created_at, NOW()) AS hace_minutos

                FROM notificaciones n

                WHERE n.usuario_id = %s

                ORDER BY n.created_at DESC

                LIMIT 20

                """,
                (usuario_id,),
            )

            notificaciones = cursor.fetchall()

        return jsonify(
            {
                "ok": True,
                "no_leidas": no_leidas,
                "notificaciones": notificaciones,
            }
        )

    except Exception:
        app.logger.exception("Error al listar notificaciones")

        return jsonify({"ok": False, "mensaje": "Error al obtener notificaciones"}), 500

    finally:
        conexion.close()


@app.route("/api/notificaciones/<int:notif_id>/leer", methods=["POST", "PUT"])
def api_marcar_notificacion_leida(notif_id):

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """

                UPDATE notificaciones

                SET leido = 1, leido_at = NOW()

                WHERE id = %s AND usuario_id = %s

                """,
                (notif_id, usuario_id),
            )

        conexion.commit()

        return jsonify({"ok": True})

    except Exception:
        app.logger.exception("Error al marcar notificación como leída")

        return jsonify(
            {"ok": False, "mensaje": "Error al actualizar notificación"}
        ), 500

    finally:
        conexion.close()


@app.route("/api/notificaciones/leer-todas", methods=["POST", "PUT"])
def api_marcar_todas_leidas():

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """

                UPDATE notificaciones

                SET leido = 1, leido_at = NOW()

                WHERE usuario_id = %s AND leido = 0

                """,
                (usuario_id,),
            )

        conexion.commit()

        return jsonify({"ok": True})

    except Exception:
        app.logger.exception("Error al marcar todas las notificaciones como leídas")

        return jsonify(
            {"ok": False, "mensaje": "Error al actualizar notificaciones"}
        ), 500

    finally:
        conexion.close()


# =====================================================================*

# MÓDULO 6: DASHBOARD Y VISTAS DEL SISTEMA*

# =====================================================================*


def obtener_datos_dashboard(empresa_id):

    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """

                SELECT COUNT(*) AS total,

                    COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,

                    COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,

                    COALESCE(SUM(estado NOT IN ('Resuelto','Cerrado')

                        AND fecha_limite IS NOT NULL AND fecha_limite < NOW()), 0) AS vencidos

                FROM tickets WHERE empresa_id = %s

            """,
                (empresa_id,),
            )

            kpis = cursor.fetchone()

            cursor.execute(
                "SELECT estado, COUNT(*) AS total FROM tickets WHERE empresa_id=%s GROUP BY estado",
                (empresa_id,),
            )

            estados = cursor.fetchall()

            cursor.execute(
                """

                SELECT p.nombre AS prioridad, COUNT(*) AS total

                FROM tickets t JOIN prioridades p ON p.id=t.prioridad_id

                WHERE t.empresa_id=%s GROUP BY p.id,p.nombre,p.nivel ORDER BY p.nivel DESC

            """,
                (empresa_id,),
            )

            prioridades = cursor.fetchall()

            cursor.execute(
                """

                SELECT u.nombre AS tecnico, COUNT(t.id) AS total

                FROM tickets t LEFT JOIN users u ON u.id=t.tecnico_id

                WHERE t.empresa_id=%s AND t.tecnico_id IS NOT NULL

                GROUP BY u.id,u.nombre ORDER BY total DESC LIMIT 8

            """,
                (empresa_id,),
            )

            tecnicos = cursor.fetchall()

            cursor.execute(
                """

                SELECT c.nombre AS categoria, COUNT(*) AS total

                FROM tickets t JOIN categorias c ON c.id=t.categoria_id

                WHERE t.empresa_id=%s GROUP BY c.id,c.nombre ORDER BY total DESC

            """,
                (empresa_id,),
            )

            categorias = cursor.fetchall()

            cursor.execute(
                """

                SELECT t.id,t.asunto,t.estado,t.created_at,p.nombre AS prioridad,u.nombre AS tecnico

                FROM tickets t JOIN prioridades p ON p.id=t.prioridad_id

                LEFT JOIN users u ON u.id=t.tecnico_id

                WHERE t.empresa_id=%s ORDER BY t.created_at DESC LIMIT 5

            """,
                (empresa_id,),
            )

            recientes = cursor.fetchall()

        return {
            "kpis": kpis,
            "estados": estados,
            "prioridades": prioridades,
            "tecnicos": tecnicos,
            "categorias": categorias,
            "recientes": recientes,
        }

    finally:
        conexion.close()

@app.route("/sla")
@login_requerido
def sla():
    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))
    
    empresa_id = session["empresa_id"]
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # Consulta oficial de la vista v_tickets ordenada por urgencia y plazos
            cursor.execute(
                """
                SELECT * FROM v_tickets 
                WHERE empresa_id = %s 
                ORDER BY urgencia DESC, minutos_restantes
                """,
                (empresa_id,)
            )
            tickets = cursor.fetchall()
    finally:
        conexion.close()

    empresa = obtener_identidad_empresa(empresa_id)

    return render_template(
        "sla.html",
        tickets=tickets,
        usuario_nombre=session.get("nombre", ""),
        usuario_rol=session.get("rol", ""),
        empresa_nombre=empresa["nombre"],
        empresa_color=empresa["color"]
    )

@app.route("/dashboard")
@login_requerido
def dashboard():

    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))

    datos = obtener_datos_dashboard(session["empresa_id"])

    empresa = obtener_identidad_empresa(session["empresa_id"])

    return render_template(
        "dashboard.html",
        usuario_nombre=session["nombre"],
        usuario_rol=session["rol"],
        datos=datos,
        empresa_nombre=empresa["nombre"],
        empresa_color=empresa["color"],
    )


@app.route("/reportes")
def reportes():

    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))

    empresa_id = session["empresa_id"]

    conexion = obtener_conexion()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """

                SELECT t.id, t.numero, t.asunto, t.descripcion, t.estado, t.created_at,

                       t.updated_at, t.fecha_limite,

                       solicitante.nombre AS solicitante,

                       COALESCE(a.nombre,'Sin área') AS area,

                       COALESCE(c.nombre,'Sin categoría') AS categoria,

                       COALESCE(p.nombre,'Sin prioridad') AS prioridad,

                       COALESCE(tecnico.nombre,'Sin asignar') AS tecnico

                FROM tickets t

                LEFT JOIN users solicitante ON solicitante.id=t.solicitante_id

                LEFT JOIN areas a ON a.id=t.area_id

                LEFT JOIN categorias c ON c.id=t.categoria_id

                LEFT JOIN prioridades p ON p.id=t.prioridad_id

                LEFT JOIN users tecnico ON tecnico.id=t.tecnico_id

                WHERE t.empresa_id=%s

                ORDER BY t.created_at DESC,t.id DESC

            """,
                (empresa_id,),
            )

            tickets = cursor.fetchall()

            cursor.execute(
                "SELECT DISTINCT nombre FROM areas WHERE empresa_id=%s AND activo=1 ORDER BY nombre",
                (empresa_id,),
            )

            areas = [r["nombre"] for r in cursor.fetchall()]

            cursor.execute(
                "SELECT nombre FROM categorias WHERE activo=1 ORDER BY nombre"
            )

            categorias = [r["nombre"] for r in cursor.fetchall()]

            cursor.execute("SELECT nombre FROM prioridades ORDER BY nivel DESC")

            prioridades = [r["nombre"] for r in cursor.fetchall()]

            cursor.execute(
                """

                SELECT DISTINCT u.nombre FROM tickets t JOIN users u ON u.id=t.tecnico_id

                WHERE t.empresa_id=%s ORDER BY u.nombre

            """,
                (empresa_id,),
            )

            tecnicos = [r["nombre"] for r in cursor.fetchall()]

    finally:
        conexion.close()

    empresa = obtener_identidad_empresa(empresa_id)

    return render_template(
        "reportes.html",
        tickets=tickets,
        areas=areas,
        categorias=categorias,
        prioridades=prioridades,
        tecnicos=tecnicos,
        usuario_nombre=session.get("nombre", ""),
        usuario_rol=session.get("rol", ""),
        empresa_nombre=empresa["nombre"],
        empresa_color=empresa["color"],
    )



# Múltiples decoradores permiten que Flask acepte la ruta con o sin .html
@app.route("/<pagina>")
@app.route("/<pagina>.html")
def pantalla(pagina):
    if pagina == "index":
        return redirect(url_for("cerrar_sesion"))
    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))
    if pagina == "dashboard":
        return redirect(url_for("dashboard"))
    if pagina == "reportes":
        return redirect(url_for("reportes"))
    try:
        # Se asegura de que, independientemente de cómo se llame a la ruta,
        # Jinja busque siempre el archivo .html en la carpeta templates
        return render_template(f"{pagina}.html")
    except TemplateNotFound:
        abort(404)


# --Tablas--
# empresas
@app.route("/api_insertar_empresa", methods=["POST"])
def api_insertar_empresa():
    rpta = dict()
    objConexion = None
    try:
        v_codigo = request.json["codigo"]
        v_nombre = request.json["nombre"]
        v_razon_social = request.json.get("razon_social")
        v_ruc = request.json.get("ruc")
        v_prefijo_ticket = request.json["prefijo_ticket"]
        v_titulo_sistema = request.json["titulo_sistema"]
        v_color_primario = request.json["color_primario"]
        v_color_secundario = request.json["color_secundario"]
        v_logo_url = request.json.get("logo_url")
        v_activo = request.json.get("activo", 1)

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = """INSERT INTO `empresas`
                     (`codigo`, `nombre`, `razon_social`, `ruc`, `prefijo_ticket`,
                      `titulo_sistema`, `color_primario`, `color_secundario`, `logo_url`, `activo`)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(
                sql,
                (
                    v_codigo,
                    v_nombre,
                    v_razon_social,
                    v_ruc,
                    v_prefijo_ticket,
                    v_titulo_sistema,
                    v_color_primario,
                    v_color_secundario,
                    v_logo_url,
                    v_activo,
                ),
            )
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id}
        rpta["message"] = "Empresa insertada correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_empresas")
def api_obtener_empresas():
    rpta = dict()
    objConexion = None
    try:
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = """SELECT `id`, `codigo`, `nombre`, `razon_social`, `ruc`, `prefijo_ticket`,
                            `titulo_sistema`, `color_primario`, `color_secundario`, `logo_url`,
                            `ultimo_ticket`, `activo`,
                            DATE_FORMAT(`created_at`, '%Y-%m-%d %H:%i:%s') AS created_at
                     FROM `empresas`"""
            cursor.execute(sql)
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Empresas obtenidas correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# empresa_dominios
@app.route("/api_insertar_empresa_dominio", methods=["POST"])
def api_insertar_empresa_dominio():
    rpta = dict()
    objConexion = None
    try:
        v_empresa_id = request.json["empresa_id"]
        v_dominio = request.json["dominio"].strip().lower()

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "INSERT INTO `empresa_dominios` (`empresa_id`, `dominio`) VALUES (%s, %s)"
            cursor.execute(sql, (v_empresa_id, v_dominio))
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id}
        rpta["message"] = "Dominio insertado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_empresa_dominios")
def api_obtener_empresa_dominios():
    rpta = dict()
    objConexion = None
    try:
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "SELECT `id`, `empresa_id`, `dominio` FROM `empresa_dominios`"
            cursor.execute(sql)
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Dominios obtenidos correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# areas
@app.route("/api_insertar_area", methods=["POST"])
def api_insertar_area():
    rpta = dict()
    objConexion = None

    try:
        datos = request.get_json()

        v_empresa_id = datos["empresa_id"]
        v_nombre = datos["nombre"]
        v_activo = datos.get("activo", 1)

        objConexion = obtener_conexion()

        with objConexion.cursor() as cursor:
            sql = """
                INSERT INTO areas (empresa_id, nombre, activo)
                VALUES (%s, %s, %s)
            """

            cursor.execute(sql, (v_empresa_id, v_nombre, v_activo))

            nuevo_id = cursor.lastrowid

        objConexion.commit()

        rpta["status"] = 1
        rpta["data"] = {
            "id": nuevo_id,
            "empresa_id": v_empresa_id,
            "nombre": v_nombre,
            "activo": v_activo,
        }
        rpta["message"] = "Area insertada correctamente"

    except Exception as e:
        if objConexion:
            objConexion.rollback()

        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)

    finally:
        if objConexion:
            objConexion.close()

    return jsonify(rpta)


@app.route("/api_obtener_areas", methods=["GET"])
def api_obtener_areas():
    rpta = dict()
    objConexion = None

    try:
        objConexion = obtener_conexion()

        with objConexion.cursor() as cursor:
            sql = """
                SELECT id, empresa_id, nombre, activo
                FROM areas
                ORDER BY id
            """

            cursor.execute(sql)
            resultado = cursor.fetchall()

        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Areas obtenidas correctamente"

    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)

    finally:
        if objConexion:
            objConexion.close()

    return jsonify(rpta)


# users
@app.route("/api_insertar_user", methods=["POST"])
def api_insertar_user():
    rpta = dict()
    objConexion = None

    try:
        datos = request.get_json()

        v_empresa_id = datos["empresa_id"]
        v_area_id = datos.get("area_id")
        v_nombre = datos["nombre"]
        v_correo = datos["correo"]
        v_password_hash = datos["password_hash"]
        v_rol = datos.get("rol", "Solicitante")
        v_activo = datos.get("activo", 1)

        objConexion = obtener_conexion()

        with objConexion.cursor() as cursor:
            sql = """
                INSERT INTO users (
                    empresa_id, area_id, nombre, correo,
                    password_hash, rol, activo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(
                sql,
                (
                    v_empresa_id,
                    v_area_id,
                    v_nombre,
                    v_correo,
                    v_password_hash,
                    v_rol,
                    v_activo,
                ),
            )

            nuevo_id = cursor.lastrowid

        objConexion.commit()

        rpta["status"] = 1
        rpta["data"] = {
            "id": nuevo_id,
            "empresa_id": v_empresa_id,
            "area_id": v_area_id,
            "nombre": v_nombre,
            "correo": v_correo,
            "rol": v_rol,
            "activo": v_activo,
        }
        rpta["message"] = "Usuario insertado correctamente"

    except Exception as e:
        if objConexion:
            objConexion.rollback()

        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)

    finally:
        if objConexion:
            objConexion.close()

    return jsonify(rpta)


@app.route("/api_obtener_users", methods=["GET"])
def api_obtener_users():
    rpta = dict()
    objConexion = None

    try:
        objConexion = obtener_conexion()

        with objConexion.cursor() as cursor:
            sql = """
                SELECT
                    id, empresa_id, area_id, nombre,
                    correo, rol, activo, ultimo_acceso,
                    created_at, updated_at
                FROM users
                ORDER BY id
            """

            cursor.execute(sql)
            resultado = cursor.fetchall()

        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Usuarios obtenidos correctamente"

    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)

    finally:
        if objConexion:
            objConexion.close()

    return jsonify(rpta)


# tokens_revocados
@app.route("/api_insertar_token_revocado", methods=["POST"])
def api_insertar_token_revocado():
    rpta = dict()
    objConexion = None
    try:
        v_jti = request.json.get("jti") or str(uuid.uuid4())
        v_usuario_id = request.json.get("usuario_id")
        v_expira_en = request.json.get("expira_en")

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "INSERT INTO `tokens_revocados` (`jti`, `usuario_id`, `expira_en`) VALUES (%s, %s, %s)"
            cursor.execute(sql, (v_jti, v_usuario_id, v_expira_en))
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id, "jti": v_jti}
        rpta["message"] = "Token revocado insertado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_tokens_revocados")
def api_obtener_tokens_revocados():
    rpta = dict()
    objConexion = None
    try:
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = """SELECT `id`, `jti`, `usuario_id`,
                            DATE_FORMAT(`expira_en`, '%Y-%m-%d %H:%i:%s') AS expira_en,
                            DATE_FORMAT(`created_at`, '%Y-%m-%d %H:%i:%s') AS created_at
                     FROM `tokens_revocados`"""
            cursor.execute(sql)
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Tokens revocados obtenidos correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# categorias
@app.route("/api_insertar_categoria", methods=["POST"])
def api_insertar_categoria():
    rpta = dict()
    objConexion = None
    try:
        v_nombre = request.json["nombre"]
        v_descripcion = request.json.get("descripcion")
        v_activo = request.json.get("activo", 1)

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "INSERT INTO `categorias` (`nombre`, `descripcion`, `activo`) VALUES (%s, %s, %s)"
            cursor.execute(sql, (v_nombre, v_descripcion, v_activo))
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id}
        rpta["message"] = "Categoría insertada correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_categorias")
def api_obtener_categorias():
    rpta = dict()
    objConexion = None
    try:
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "SELECT `id`, `nombre`, `descripcion`, `activo` FROM `categorias`"
            cursor.execute(sql)
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Categorías obtenidas correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# prioridades
@app.route("/api_insertar_prioridad", methods=["POST"])
def api_insertar_prioridad():
    rpta = dict()
    objConexion = None
    try:
        v_id = request.json["id"]
        v_nombre = request.json["nombre"]
        v_sla_horas = request.json["sla_horas"]
        v_nivel = request.json["nivel"]

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "INSERT INTO prioridades (id, nombre, sla_horas, nivel) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (v_id, v_nombre, v_sla_horas, v_nivel))
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": v_id}
        rpta["message"] = "Prioridad insertada correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_prioridades")
def api_obtener_prioridades():
    rpta = dict()
    objConexion = None
    try:
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = "SELECT id, nombre, sla_horas, nivel FROM prioridades ORDER BY nivel DESC"
            cursor.execute(sql)
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Prioridades obtenidas correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# ticlkets
@app.route("/api_insertar_ticket", methods=["POST"])
def api_insertar_ticket():
    rpta = dict()
    objConexion = None
    try:
        v_solicitante = request.json["solicitante_id"]
        v_categoria = request.json["categoria_id"]
        v_prioridad = request.json["prioridad_id"]
        v_asunto = request.json["asunto"]
        v_descripcion = request.json["descripcion"]

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            cursor.execute(
                "SELECT empresa_id, area_id FROM users WHERE id = %s AND activo = 1",
                (v_solicitante,),
            )
            usuario = cursor.fetchone()
            if not usuario:
                raise ValueError("Solicitante no existe o está inactivo")
            empresa_id = usuario["empresa_id"]
            area_id = usuario["area_id"]

            cursor.execute(
                "SELECT sla_horas FROM prioridades WHERE id = %s", (v_prioridad,)
            )
            prio = cursor.fetchone()
            if not prio:
                raise ValueError("Prioridad no válida")
            sla_horas = prio["sla_horas"]

            cursor.execute(
                "UPDATE empresas SET ultimo_ticket = LAST_INSERT_ID(ultimo_ticket + 1) "
                "WHERE id = %s",
                (empresa_id,),
            )
            cursor.execute("SELECT LAST_INSERT_ID() AS numero")
            numero = cursor.fetchone()["numero"]

            sql = (
                "INSERT INTO tickets (empresa_id, numero, area_id, solicitante_id, categoria_id, "
                "prioridad_id, asunto, descripcion, fecha_limite) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW() + INTERVAL %s HOUR)"
            )
            cursor.execute(
                sql,
                (
                    empresa_id,
                    numero,
                    area_id,
                    v_solicitante,
                    v_categoria,
                    v_prioridad,
                    v_asunto,
                    v_descripcion,
                    sla_horas,
                ),
            )
            nuevo_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_nuevo, comentario) "
                "VALUES (%s, %s, 'CREACION', 'Abierto', 'Ticket registrado.')",
                (nuevo_id, v_solicitante),
            )

            cursor.execute(
                "SELECT CONCAT(prefijo_ticket, '-', LPAD(%s, 4, '0')) AS codigo "
                "FROM empresas WHERE id = %s",
                (numero, empresa_id),
            )
            codigo = cursor.fetchone()["codigo"]
            cursor.execute(
                "INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje) "
                "SELECT id, 'NUEVO_TICKET', %s, %s, %s FROM users "
                "WHERE empresa_id = %s AND rol = 'Administrador' AND activo = 1 AND id <> %s",
                (
                    nuevo_id,
                    "Nuevo ticket " + codigo,
                    v_asunto,
                    empresa_id,
                    v_solicitante,
                ),
            )
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id, "codigo": codigo}
        rpta["message"] = "Ticket insertado correctamente"
    except Exception as e:
        if objConexion:
            objConexion.rollback()
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_tickets")
def api_obtener_tickets():
    rpta = dict()
    objConexion = None
    try:
        v_empresa = request.args.get("empresa_id")

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = (
                "SELECT id, codigo, asunto, estado, area, categoria, prioridad, solicitante, "
                "tecnico, created_at, fecha_limite, semaforo, minutos_restantes "
                "FROM v_tickets WHERE empresa_id = %s ORDER BY urgencia DESC, minutos_restantes"
            )
            cursor.execute(sql, (v_empresa,))
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Tickets obtenidos correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# ticket_evidencias
@app.route("/api_insertar_evidencia", methods=["POST"])
def api_insertar_evidencia():
    rpta = dict()
    objConexion = None
    try:
        v_ticket_id = request.json["ticket_id"]
        v_orden = request.json["orden"]
        v_nombre_original = request.json["nombre_original"]
        v_nombre_archivo = request.json["nombre_archivo"]
        v_ruta = request.json["ruta"]
        v_mime_type = request.json["mime_type"]
        v_tamano_bytes = request.json["tamano_bytes"]
        v_subido_por = request.json["subido_por"]

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = (
                "INSERT INTO ticket_evidencias (ticket_id, orden, nombre_original, nombre_archivo, "
                "ruta, mime_type, tamano_bytes, subido_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            cursor.execute(
                sql,
                (
                    v_ticket_id,
                    v_orden,
                    v_nombre_original,
                    v_nombre_archivo,
                    v_ruta,
                    v_mime_type,
                    v_tamano_bytes,
                    v_subido_por,
                ),
            )
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id}
        rpta["message"] = "Evidencia insertada correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_evidencias")
def api_obtener_evidencias():
    rpta = dict()
    objConexion = None
    try:
        v_ticket_id = request.args.get("ticket_id")
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = (
                "SELECT id, ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type, "
                "tamano_bytes, subido_por FROM ticket_evidencias WHERE ticket_id = %s ORDER BY orden"
            )
            cursor.execute(sql, (v_ticket_id,))
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Evidencias obtenidas correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# ticket_historial
@app.route("/api_insertar_historial", methods=["POST"])
def api_insertar_historial():
    rpta = dict()
    objConexion = None
    try:
        v_ticket_id = request.json["ticket_id"]
        v_usuario_id = request.json["usuario_id"]
        v_tipo = request.json["tipo"]
        v_estado_anterior = request.json.get("estado_anterior")
        v_estado_nuevo = request.json.get("estado_nuevo")
        v_tecnico_anterior = request.json.get("tecnico_anterior_id")
        v_tecnico_nuevo = request.json.get("tecnico_nuevo_id")
        v_comentario = request.json["comentario"]

        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            sql = (
                "INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, "
                "tecnico_anterior_id, tecnico_nuevo_id, comentario) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            cursor.execute(
                sql,
                (
                    v_ticket_id,
                    v_usuario_id,
                    v_tipo,
                    v_estado_anterior,
                    v_estado_nuevo,
                    v_tecnico_anterior,
                    v_tecnico_nuevo,
                    v_comentario,
                ),
            )
            nuevo_id = cursor.lastrowid
        objConexion.commit()
        rpta["status"] = 1
        rpta["data"] = {"id": nuevo_id}
        rpta["message"] = "Historial registrado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


@app.route("/api_obtener_historial", methods=["GET"])
def api_obtener_historial():
    rpta = dict()
    objConexion = None
    try:
        v_ticket_id = request.args.get("ticket_id")
        objConexion = obtener_conexion()
        with objConexion.cursor() as cursor:
            if v_ticket_id:
                cursor.execute(
                    "SELECT * FROM ticket_historial WHERE ticket_id = %s",
                    (v_ticket_id,),
                )
            else:
                cursor.execute("SELECT * FROM ticket_historial")
            resultado = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = resultado
        rpta["message"] = "Historial listado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = []
        rpta["message"] = "Error: " + repr(e)
    finally:
        if objConexion:
            objConexion.close()
    return jsonify(rpta)


# notificaciones
@app.route("/api_insertar_notificacion", methods=["POST"])
def api_insertar_notificacion():
    rpta = dict()
    try:
        objConexion = obtener_conexion()

        v_userid = request.json["usuario_id"]
        v_tipo = request.json["tipo"]
        v_titulo = request.json["titulo"]
        v_referencia_ticket = request.json.get("referencia_ticket")
        v_mensaje = request.json.get("mensaje")

        with objConexion:
            with objConexion.cursor() as cursor:
                sql = """
                    INSERT INTO `notificaciones`
                    (`usuario_id`, `tipo`, `referencia_ticket`, `titulo`, `mensaje`)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(
                    sql, (v_userid, v_tipo, v_referencia_ticket, v_titulo, v_mensaje)
                )
            objConexion.commit()

        rpta["status"] = 1
        rpta["data"] = {}
        rpta["message"] = "Notificación insertada correctamente"

    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)

    return jsonify(rpta)


@app.route("/api_obtenernotificaciones")
def api_obtenernotificaciones():
    rpta = dict()
    try:
        objConexion = obtener_conexion()
        with objConexion:
            with objConexion.cursor() as cursor:
                sql = "SELECT `id`, `usuario_id`, `tipo`, `referencia_ticket`, `titulo`, `mensaje`, `leido`, `leido_at` FROM notificaciones"
                cursor.execute(sql)
                result = cursor.fetchall()
        rpta["status"] = 1
        rpta["data"] = result
        rpta["message"] = "Notificacion listado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    return jsonify(rpta)


if __name__ == "__main__":
    app.run(debug=True)