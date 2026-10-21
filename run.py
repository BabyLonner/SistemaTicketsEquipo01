import os
import unicodedata
import bcrypt
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound

from db import obtener_conexion
from tickets import tickets_bp

load_dotenv()
app = Flask(__name__)
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
                cursor.execute("""
                    SELECT id, empresa_id, nombre, correo, password_hash, rol, activo
                    FROM users WHERE correo = %s LIMIT 1
                """, (correo,))
                usuario = cursor.fetchone()
            if not usuario or not usuario["activo"]:
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))
            if not bcrypt.checkpw(clave.encode("utf-8"), usuario["password_hash"].encode("utf-8")):
                flash("Correo o contraseña incorrectos.", "error")
                return redirect(url_for("inicio"))
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["nombre"] = usuario["nombre"]
            session["correo"] = usuario["correo"]
            session["rol"] = usuario["rol"]
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


def obtener_datos_dashboard(empresa_id):
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(estado = 'Abierto'), 0) AS abiertos,
                    COALESCE(SUM(estado = 'Resuelto'), 0) AS resueltos,
                    COALESCE(SUM(estado NOT IN ('Resuelto','Cerrado')
                        AND fecha_limite IS NOT NULL AND fecha_limite < NOW()), 0) AS vencidos
                FROM tickets WHERE empresa_id = %s
            """, (empresa_id,))
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
