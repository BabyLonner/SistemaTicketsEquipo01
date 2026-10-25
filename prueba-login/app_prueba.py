import os
import sys
import bcrypt
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

# Permitir importar db.py desde la carpeta raíz del proyecto
RUTA_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RUTA_RAIZ)

from db import obtener_conexion

# Usamos la carpeta static original para leer /static/img/logos/...
app = Flask(
    __name__,
    template_folder="templates",
    static_folder=os.path.join(RUTA_RAIZ, "static"),
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave-prueba-login")


@app.route("/api/identidad-empresa", methods=["GET"])
def api_identidad_empresa():
    """Devuelve el logo, título y colores según el dominio del correo ingresado."""
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
                # Usamos v_usuarios_sesion para traer los datos del usuario + logo y colores de su empresa
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

            # Guardamos en sesión tanto los datos del usuario como el logo de su empresa
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

            return redirect(url_for("bienvenida_empresa"))

        except Exception:
            app.logger.exception("Error durante el inicio de sesión")
            flash("No se pudo completar el acceso. Inténtalo nuevamente.", "error")
            return redirect(url_for("inicio"))
        finally:
            conexion.close()

    if session.get("usuario_id"):
        return redirect(url_for("bienvenida_empresa"))

    return render_template("index_moderno.html")


@app.route("/bienvenida")
def bienvenida_empresa():
    if not session.get("usuario_id"):
        return redirect(url_for("inicio"))
    return render_template("bienvenida_test.html")


@app.route("/cerrar-sesion")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("inicio"))


if __name__ == "__main__":
    # Corre en el puerto 5001 para no chocar con tu proyecto principal
    app.run(debug=True, port=5001)