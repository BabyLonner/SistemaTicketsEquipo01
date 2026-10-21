import os
<<<<<<< HEAD
import unicodedata
import bcrypt
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

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
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
from jinja2 import TemplateNotFound

from db import obtener_conexion
from tickets import tickets_bp

load_dotenv()
app = Flask(__name__)
<<<<<<< HEAD
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave-local-solo-desarrollo")
app.register_blueprint(tickets_bp)


# Colores distintivos por empresa. Las claves se comparan sin tildes ni mayúsculas.
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
    nombre = "".join(caracter for caracter in nombre if unicodedata.category(caracter) != "Mn")
    return " ".join(nombre.casefold().split())


def obtener_identidad_empresa(empresa_id):
    """
    Obtiene el nombre de la empresa del usuario conectado y el color distintivo.
    Asume que la tabla empresas contiene las columnas id y nombre.
    """
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT nombre FROM empresas WHERE id = %s LIMIT 1", (empresa_id,))
            empresa = cursor.fetchone()

        nombre = empresa["nombre"] if empresa and empresa.get("nombre") else "Empresa"
        clave = normalizar_nombre_empresa(nombre)
        color = COLORES_EMPRESAS.get(clave, "#2672C7")
        return {"nombre": nombre, "color": color}
    finally:
        conexion.close()


=======
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "clave-local-solo-desarrollo",
)

# =====================================================================
# REGISTRO DE BLUEPRINTS
# =====================================================================
# Módulo de tickets: registro con evidencias (API en /api/tickets)
app.register_blueprint(tickets_bp)


# =====================================================================
# MIDDLEWARES Y UTILIDADES DE SESIÓN
# =====================================================================
def login_requerido(f):
    """Decorador para proteger rutas que requieren sesión activa."""
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("inicio"))
        return f(*args, **kwargs)
    return decorador


@app.context_processor
def inyectar_datos_globales():
    """
    Inyecta automáticamente las variables de sesión en TODOS los templates HTML.
    Así todas las vistas tienen acceso al nombre, rol y colores de la empresa.
    """
    return {
        "usuario_id": session.get("usuario_id"),
        "usuario_nombre": session.get("nombre"),
        "usuario_rol": session.get("rol"),
        "usuario_area": session.get("area"),
        "empresa_id": session.get("empresa_id"),
        "empresa_nombre": session.get("empresa_nombre"),
        "titulo_sistema": session.get("titulo_sistema", "Mesa de Ayuda TI"),
        "color_primario": session.get("color_primario", "#0077B6"),
        "color_secundario": session.get("color_secundario", "#D6EEF8"),
        "logo_url": session.get("logo_url"),
    }


# =====================================================================
# MÓDULO 1: AUTENTICACIÓN Y ACCESO
# =====================================================================
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
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
<<<<<<< HEAD
                cursor.execute("""
                    SELECT id, empresa_id, nombre, correo, password_hash, rol, activo
                    FROM users WHERE correo = %s LIMIT 1
                """, (correo,))
                usuario = cursor.fetchone()
            if not usuario or not usuario["activo"]:
                flash("Correo o contraseña incorrectos.", "error")
=======
                # Usamos la vista v_usuarios_sesion de mesa_ayuda_ti.sql
                cursor.execute(
                    """
                    SELECT id, nombre, correo, password_hash, rol, activo,
                           area_id, area, empresa_id, empresa, titulo_sistema,
                           color_primario, color_secundario, logo_url, empresa_activa
                    FROM v_usuarios_sesion
                    WHERE correo = %s
                    LIMIT 1
                    """,
                    (correo,),
                )
                usuario = cursor.fetchone()

            if not usuario or not usuario["activo"] or not usuario["empresa_activa"]:
                flash("Correo o contraseña incorrectos, o cuenta inactiva.", "error")
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
                return redirect(url_for("inicio"))
            if not bcrypt.checkpw(clave.encode("utf-8"), usuario["password_hash"].encode("utf-8")):
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))
<<<<<<< HEAD
=======

            # Guardar datos del usuario y personalización de su empresa en la sesión
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["nombre"] = usuario["nombre"]
            session["correo"] = usuario["correo"]
            session["rol"] = usuario["rol"]
<<<<<<< HEAD
=======
            session["area_id"] = usuario["area_id"]
            session["area"] = usuario["area"]
            session["empresa_nombre"] = usuario["empresa"]
            session["titulo_sistema"] = usuario["titulo_sistema"]
            session["color_primario"] = usuario["color_primario"]
            session["color_secundario"] = usuario["color_secundario"]
            session["logo_url"] = usuario["logo_url"]

>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
            with conexion.cursor() as cursor:
                cursor.execute("UPDATE users SET ultimo_acceso = NOW() WHERE id = %s", (usuario["id"],))
            conexion.commit()
            return redirect(url_for("dashboard"))
        except Exception:
            app.logger.exception("Error durante el inicio de sesión")
            flash("No se pudo completar el acceso. Inténtalo nuevamente.", "error")
            return redirect(url_for("inicio"))
        finally:
            conexion.close()
    if session.get("usuario_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/cerrar-sesion")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("inicio"))


# =====================================================================
# MÓDULO 5: API REST DE NOTIFICACIONES INTERNAS
# =====================================================================
@app.route("/api/notificaciones", methods=["GET"])
def api_listar_notificaciones():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # 1. Cantidad de notificaciones no leídas para el globo rojo (badge)
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

            # 2. Últimas 20 notificaciones del usuario con código de ticket si aplica
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

        return jsonify({
            "ok": True,
            "no_leidas": no_leidas,
            "notificaciones": notificaciones,
        })
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
        return jsonify({"ok": False, "mensaje": "Error al actualizar notificación"}), 500
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
        return jsonify({"ok": False, "mensaje": "Error al actualizar notificaciones"}), 500
    finally:
        conexion.close()


# =====================================================================
# MÓDULO 6: DASHBOARD Y VISTAS DEL SISTEMA
# =====================================================================
def obtener_datos_dashboard(empresa_id):
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
<<<<<<< HEAD
            cursor.execute("""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,
                    COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,
                    COALESCE(SUM(estado NOT IN ('Resuelto','Cerrado')
                        AND fecha_limite IS NOT NULL AND fecha_limite < NOW()), 0) AS vencidos
                FROM tickets WHERE empresa_id = %s
            """, (empresa_id,))
=======
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,
                    COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,
                    COALESCE(
                        SUM(
                            estado NOT IN ('Resuelto', 'Cerrado')
                            AND fecha_limite IS NOT NULL
                            AND fecha_limite < NOW()
                        ), 0
                    ) AS vencidos
                FROM tickets
                WHERE empresa_id = %s
                """,
                (empresa_id,),
            )
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
            kpis = cursor.fetchone()
            cursor.execute("SELECT estado, COUNT(*) AS total FROM tickets WHERE empresa_id=%s GROUP BY estado", (empresa_id,))
            estados = cursor.fetchall()
            cursor.execute("""
                SELECT p.nombre AS prioridad, COUNT(*) AS total
                FROM tickets t JOIN prioridades p ON p.id=t.prioridad_id
                WHERE t.empresa_id=%s GROUP BY p.id,p.nombre,p.nivel ORDER BY p.nivel DESC
            """, (empresa_id,))
            prioridades = cursor.fetchall()
            cursor.execute("""
                SELECT u.nombre AS tecnico, COUNT(t.id) AS total
                FROM tickets t LEFT JOIN users u ON u.id=t.tecnico_id
                WHERE t.empresa_id=%s AND t.tecnico_id IS NOT NULL
                GROUP BY u.id,u.nombre ORDER BY total DESC LIMIT 8
            """, (empresa_id,))
            tecnicos = cursor.fetchall()
            cursor.execute("""
                SELECT c.nombre AS categoria, COUNT(*) AS total
                FROM tickets t JOIN categorias c ON c.id=t.categoria_id
                WHERE t.empresa_id=%s GROUP BY c.id,c.nombre ORDER BY total DESC
            """, (empresa_id,))
            categorias = cursor.fetchall()
            cursor.execute("""
                SELECT t.id,t.asunto,t.estado,t.created_at,p.nombre AS prioridad,u.nombre AS tecnico
                FROM tickets t JOIN prioridades p ON p.id=t.prioridad_id
                LEFT JOIN users u ON u.id=t.tecnico_id
                WHERE t.empresa_id=%s ORDER BY t.created_at DESC LIMIT 5
            """, (empresa_id,))
            recientes = cursor.fetchall()
        return {"kpis": kpis, "estados": estados, "prioridades": prioridades,
                "tecnicos": tecnicos, "categorias": categorias, "recientes": recientes}
    finally:
        conexion.close()


@app.route("/dashboard")
@login_requerido
def dashboard():
    datos = obtener_datos_dashboard(session["empresa_id"])
<<<<<<< HEAD
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
            cursor.execute("""
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
            """, (empresa_id,))
            tickets = cursor.fetchall()
            cursor.execute("SELECT DISTINCT nombre FROM areas WHERE empresa_id=%s AND activo=1 ORDER BY nombre", (empresa_id,))
            areas = [r["nombre"] for r in cursor.fetchall()]
            cursor.execute("SELECT nombre FROM categorias WHERE activo=1 ORDER BY nombre")
            categorias = [r["nombre"] for r in cursor.fetchall()]
            cursor.execute("SELECT nombre FROM prioridades ORDER BY nivel DESC")
            prioridades = [r["nombre"] for r in cursor.fetchall()]
            cursor.execute("""
                SELECT DISTINCT u.nombre FROM tickets t JOIN users u ON u.id=t.tecnico_id
                WHERE t.empresa_id=%s ORDER BY u.nombre
            """, (empresa_id,))
            tecnicos = [r["nombre"] for r in cursor.fetchall()]
    finally:
        conexion.close()
    empresa = obtener_identidad_empresa(empresa_id)
    return render_template("reportes.html", tickets=tickets, areas=areas, categorias=categorias,
                           prioridades=prioridades, tecnicos=tecnicos,
                           usuario_nombre=session.get("nombre", ""), usuario_rol=session.get("rol", ""),
                           empresa_nombre=empresa["nombre"], empresa_color=empresa["color"])


@app.route("/cerrar-sesion")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("inicio"))


=======
    return render_template("dashboard.html", datos=datos)


# Rutas limpias y con .html para las pantallas del menú
# (tickets.html, nuevo_ticket.html, notificaciones.html, etc.)
@app.route("/<pagina>")
>>>>>>> ce55750865b9393c7726d7b7ee40512a9194db7e
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
        return render_template(f"{pagina}.html")
    except TemplateNotFound:
        abort(404)


if __name__ == "__main__":
    app.run(debug=True)