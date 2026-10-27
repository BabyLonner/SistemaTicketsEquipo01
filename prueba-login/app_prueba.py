import os
import sys
import bcrypt
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from datetime import datetime
from db import obtener_conexion

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

@app.route("/api/tickets", methods=["GET"])
def api_listar_tickets():
    """Lista los tickets según los filtros o permisos de la sesión actual."""
    if not session.get("usuario_id"):
        return jsonify({"error": "No autorizado"}), 401

    mios = request.args.get("mios", "0")
    limite = int(request.args.get("limite", 200))
    empresa_usuario = session.get("empresa_nombre")
    rol_usuario = session.get("rol")
    usuario_id = session.get("usuario_id")

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # Construcción dinámica según rol (Administrador, Técnico, Solicitante)
            sql = """
                SELECT t.id, t.asunto, t.descripcion, t.categoria, t.prioridad, 
                       t.estado, t.empresa, t.created_at, t.updated_at,
                       s.nombre AS solicitante, 
                       tec.nombre AS tecnico
                FROM tickets t
                JOIN users s ON t.solicitante_id = s.id
                LEFT JOIN users tec ON t.tecnico_id = tec.id
                WHERE t.empresa = %s
            """
            params = [empresa_usuario]

            if rol_usuario == "Solicitante" or mios == "1":
                sql += " AND t.solicitante_id = %s"
                params.append(usuario_id)
            elif rol_usuario == "Técnico":
                # Los técnicos pueden ver los asignados a ellos o sin asignar
                pass # Dependiendo de tu regla de negocio

            sql += " ORDER BY t.created_at DESC LIMIT %s"
            params.append(limite)

            cursor.execute(sql, tuple(params))
            tickets = cursor.fetchall()

            # Opcional: Agregar información de evidencias (fotos) para cada ticket
            for t in tickets:
                cursor.execute("""
                    SELECT id, archivo AS imagen_url, miniatura AS miniatura_url, nombre_original AS nombre
                    FROM ticket_fotos WHERE ticket_id = %s
                """, (t["id"],))
                fotos = cursor.fetchall()
                t["evidencias"] = fotos
                t["total_evidencias"] = len(fotos)
                if fotos:
                    t["miniatura_url"] = fotos[0]["miniatura_url"]
                    t["imagen_url"] = fotos[0]["imagen_url"]
                else:
                    t["miniatura_url"] = None
                    t["imagen_url"] = None

        return jsonify({"ok": True, "tickets": tickets})
    except Exception as e:
        app.logger.exception("Error al listar tickets")
        return jsonify({"error": "Error interno al obtener los tickets"}), 500
    finally:
        conexion.close()


@app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
def api_detalle_ticket(ticket_id):
    """Obtiene el detalle completo de un ticket específico junto con sus evidencias."""
    if not session.get("usuario_id"):
        return jsonify({"error": "No autorizado"}), 401

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT t.id, t.asunto, t.descripcion, t.categoria, t.prioridad, 
                       t.estado, t.empresa, t.created_at, t.updated_at,
                       s.nombre AS solicitante, s.email AS solicitante_correo, s.area,
                       tec.nombre AS tecnico
                FROM tickets t
                JOIN users s ON t.solicitante_id = s.id
                LEFT JOIN users tec ON t.tecnico_id = tec.id
                WHERE t.id = %s
            """, (ticket_id,))
            ticket = cursor.fetchone()

            if not ticket:
                return jsonify({"error": "Ticket no encontrado"}), 404

            # Obtener evidencias fotográficas asociadas
            cursor.execute("""
                SELECT id, archivo AS imagen_url, miniatura AS miniatura_url, nombre_original AS nombre
                FROM ticket_fotos WHERE ticket_id = %s
            """, (ticket_id,))
            ticket["evidencias"] = cursor.fetchall()

        return jsonify({"ok": True, "ticket": ticket})
    except Exception as e:
        app.logger.exception("Error al obtener detalle del ticket")
        return jsonify({"error": "Error interno"}), 500
    finally:
        conexion.close()


@app.route("/api/tickets/<int:ticket_id>/historial", methods=["GET"])
def api_historial_ticket(ticket_id):
    """Devuelve la línea de tiempo de cambios e interacciones del ticket[cite: 43]."""
    if not session.get("usuario_id"):
        return jsonify({"error": "No autorizado"}), 401

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT h.id, h.tipo, h.estado_anterior, h.estado_nuevo, h.texto AS comentario, 
                       h.created_at, u.nombre AS usuario, u.rol AS usuario_rol
                FROM ticket_historial h
                JOIN users u ON h.usuario_id = u.id
                WHERE h.ticket_id = %s
                ORDER BY h.created_at DESC
            """, (ticket_id,))
            historial = cursor.fetchall()

        return jsonify({"ok": True, "historial": historial})
    except Exception as e:
        app.logger.exception("Error al obtener el historial")
        return jsonify({"error": "Error interno"}), 500
    finally:
        conexion.close()

@app.route("/api/sla/metricas", methods=["GET"])
def api_sla_metricas():
    if not session.get("usuario_id"):
        return jsonify({"error": "No autorizado"}), 401

    empresa_usuario = session.get("empresa_nombre")
    conexion = obtener_conexion()
    
    try:
        with conexion.cursor() as cursor:
            # Consultamos los tickets de la empresa activa
            cursor.execute("""
                SELECT id, asunto, prioridad, estado, created_at
                FROM tickets
                WHERE empresa = %s
            """, (empresa_usuario,))
            tickets = cursor.fetchall()

            en_tiempo = 0
            por_vencer = 0
            vencidos = 0
            ahora = datetime.now()

            for t in tickets:
                # Si el ticket ya fue resuelto o cerrado, cuenta como cumplido/en tiempo
                if t["estado"] in ["Resuelto", "Cerrado"]:
                    en_tiempo += 1
                    continue
                
                # Umbrales basados estricta y exactamente en la configuración visual:
                # Alta: 8 horas | Media: 24 horas | Baja: 72 horas
                prio = t["prioridad"]
                if prio == "Alta":
                    limite_horas = 8
                elif prio == "Media":
                    limite_horas = 24
                else:
                    limite_horas = 72  # Baja por defecto
                
                # Calcular las horas transcurridas desde la creación del ticket
                delta_horas = (ahora - t["created_at"]).total_seconds() / 3600
                
                if delta_horas > limite_horas:
                    vencidos += 1
                elif delta_horas >= (limite_horas * 0.8):  # Si supera el 80% del tiempo se marca como "Por vencer"
                    por_vencer += 1
                else:
                    en_tiempo += 1

            total = len(tickets)
            cumplimiento = round((en_tiempo / total * 100) if total > 0 else 100)

            return jsonify({
                "ok": True,
                "total": total,
                "cumplimiento": cumplimiento,
                "en_tiempo": en_tiempo,
                "por_vencer": por_vencer,
                "vencidos": vencidos
            })
    except Exception as e:
        app.logger.exception("Error al calcular métricas de SLA")
        return jsonify({"error": "Error interno"}), 500
    finally:
        conexion.close()

if __name__ == "__main__":
    # Corre en el puerto 5001 para no chocar con tu proyecto principal
    app.run(debug=True, port=5001)