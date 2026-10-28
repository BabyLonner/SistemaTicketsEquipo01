"""
MÓDULO 3 (avance 2) — Etiquetas QR por equipo
=============================================

Objetivo: cada equipo informático tiene una etiqueta QR. Al escanearla, el formulario
de Nuevo Ticket se abre ya vinculado a ese equipo, con su ubicación y su historial.

Qué lleva el QR (y qué NO):
  Solo una URL corta con un identificador aleatorio:   https://.../qr/kdJ8LIBx3sO0He6u
  NUNCA el nombre, la serie, la ubicación ni datos personales. Si alguien fotografía la etiqueta
  no obtiene información; para ver el equipo hay que iniciar sesión en el sistema.

Cómo se evita que un QR alterado apunte a otro equipo:
  1. El identificador (qr_token) es aleatorio (secrets.token_urlsafe, 96 bits). No es el id 1, 2, 3…
     así que cambiar una letra no lleva a "el equipo siguiente": casi seguro no existe.
  2. El servidor busca el token SOLO dentro de la empresa del usuario en sesión.
     Un QR de otra empresa (o inventado) se rechaza.
  3. El escáner solo acepta QR cuyo enlace sea de este mismo sistema (mismo dominio).
  4. Si una etiqueta se pierde o se sospecha que fue cambiada, el administrador pulsa
     "Regenerar QR": el token cambia y la etiqueta vieja deja de funcionar.

Tecnología:
  - Pantalla: qrcode.js dibuja el QR en el navegador (nivel de corrección H = 30 %).
  - PDF de etiquetas: ReportLab (ya lo usa el módulo de reportes), mismo contenido y nivel H.
  - Lectura: html5-qrcode usa la cámara del celular o la laptop (necesita HTTPS o localhost).

Rutas:
  GET    /api/equipos                       lista de equipos de la empresa (Admin y Técnico)
  POST   /api/equipos                       registrar equipo (Admin)
  PUT    /api/equipos/<id>                  editar equipo (Admin)
  DELETE /api/equipos/<id>                  dar de baja (Admin)
  POST   /api/equipos/<id>/regenerar-qr     nuevo token; la etiqueta anterior deja de servir (Admin)
  GET    /api/equipos/etiquetas.pdf?ids=…   PDF con las etiquetas para imprimir (Admin y Técnico)
  GET    /api/equipos/qr/<token>            lo que se muestra al escanear: equipo + historial (todos)
  GET    /api/tickets/<id>/equipo           equipo vinculado a un ticket (detalle del ticket)
  GET    /qr/<token>                        enlace del QR: abre Nuevo Ticket con el equipo
                                            (si no hay sesión, pide login y después vuelve aquí)
"""
import io
import os
import re
import secrets

import pymysql
from flask import Blueprint, current_app, g, jsonify, redirect, request, send_file, url_for

import config

from db import conexion, consultar
from tickets import ROL_ADMIN, ROL_TECNICO, ErrorRegla, Ticket, login_requerido, puede_ver

equipos_bp = Blueprint("equipos", __name__)

TIPOS = ("Laptop", "PC de escritorio", "Impresora", "Monitor", "Proyector", "Equipo de red", "Teléfono", "Otro")
PATRON_TOKEN = re.compile(r"^[A-Za-z0-9_-]{12,24}$")
PATRON_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,29}$")


# =====================================================================
#  Utilidades
# =====================================================================
def nuevo_token():
    """16 caracteres aleatorios (96 bits). Imposible de adivinar o "contar"."""
    return secrets.token_urlsafe(12)


def _es_local(url):
    return re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", url or "") is not None


def url_publica():
    """Dirección del sistema que va dentro del QR (la misma variable del módulo 4).
    Si APP_URL_PUBLICA dice localhost/127.0.0.1 pero el sistema se abrió con la IP del WiFi
    (p. ej. http://192.168.0.105:5000), se usa la IP: 127.0.0.1 no sirve en el celular."""
    base = (os.getenv("APP_URL_PUBLICA") or "").strip().rstrip("/")
    actual = request.host_url.rstrip("/")
    if not base or (_es_local(base) and not _es_local(actual)):
        return actual
    return base


@equipos_bp.app_context_processor
def _url_publica_en_plantillas():
    """Nuevo Ticket necesita saber qué dirección llevan las etiquetas para aceptarlas
    aunque la laptop esté abierta con 127.0.0.1 y la etiqueta diga 192.168.x.x."""
    try:
        return {"url_publica_qr": url_publica()}
    except RuntimeError:
        return {}


def enlace_qr(token):
    """Lo único que va dentro del QR. Corto = QR con menos módulos = se lee mejor."""
    return f"{url_publica()}/qr/{token}"


def _texto(datos, campo, maximo, obligatorio=False, minimo=0):
    valor = " ".join(str(datos.get(campo) or "").split())
    if obligatorio and len(valor) < max(minimo, 1):
        return valor, f"Este campo es obligatorio{f' (mínimo {minimo} caracteres)' if minimo > 1 else ''}."
    if len(valor) > maximo:
        return valor, f"Máximo {maximo} caracteres."
    return valor, None


def _solo(*roles):
    if g.usuario["rol"] not in roles:
        return jsonify(error="Tu rol no tiene permiso para esta acción."), 403
    return None


def _equipo_json(e, con_qr=True):
    datos = {
        "id": e["id"],
        "codigo": e["codigo"],
        "nombre": e["nombre"],
        "tipo": e["tipo"],
        "marca": e["marca"],
        "modelo": e["modelo"],
        "serie": e["serie"],
        "area_id": e["area_id"],
        "area": e["area"],
        "ubicacion": e["ubicacion"],
        "activo": bool(e["activo"]),
        "total_tickets": int(e.get("total_tickets") or 0),
        "tickets_pendientes": int(e.get("tickets_pendientes") or 0),
    }
    if con_qr:
        datos["qr_url"] = enlace_qr(e["qr_token"])
    return datos


SQL_EQUIPOS = """
    SELECT q.*, a.nombre AS area,
           (SELECT COUNT(*) FROM tickets t WHERE t.equipo_id = q.id) AS total_tickets,
           (SELECT COUNT(*) FROM tickets t WHERE t.equipo_id = q.id
                AND t.estado IN ('Abierto','En proceso')) AS tickets_pendientes
      FROM equipos q
      LEFT JOIN areas a ON a.id = q.area_id
"""


def _equipo(equipo_id):
    return consultar(SQL_EQUIPOS + " WHERE q.id = %s AND q.empresa_id = %s",
                     (equipo_id, g.usuario["empresa_id"]), uno=True)


def _historial(equipo_id, limite=10):
    """Incidencias anteriores del equipo (las más recientes primero)."""
    filas = consultar(
        """SELECT t.id, CONCAT(e.prefijo_ticket, '-', LPAD(t.numero, 4, '0')) AS codigo,
                  t.asunto, t.estado, t.created_at, p.nombre AS prioridad,
                  COALESCE(u.nombre, 'Sin asignar') AS tecnico
             FROM tickets t
             JOIN empresas e    ON e.id = t.empresa_id
             JOIN prioridades p ON p.id = t.prioridad_id
             LEFT JOIN users u  ON u.id = t.tecnico_id
            WHERE t.equipo_id = %s
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT %s""",
        (equipo_id, limite),
    )
    return [{**f, "created_at": f["created_at"].isoformat(timespec="seconds")} for f in filas]


def _validar(datos):
    """Limpia y valida el formulario del equipo. Devuelve (limpios, errores)."""
    errores = {}
    limpios = {}
    limpios["codigo"], err = _texto(datos, "codigo", 30, obligatorio=True)
    limpios["codigo"] = limpios["codigo"].upper()
    if err:
        errores["codigo"] = err
    elif not PATRON_CODIGO.match(limpios["codigo"]):
        errores["codigo"] = "Usa letras, números y guiones. Ej.: AGF-PC-002"
    limpios["nombre"], err = _texto(datos, "nombre", 100, obligatorio=True, minimo=3)
    if err:
        errores["nombre"] = err
    limpios["ubicacion"], err = _texto(datos, "ubicacion", 120, obligatorio=True, minimo=3)
    if err:
        errores["ubicacion"] = err
    for campo, maximo in (("marca", 50), ("modelo", 60), ("serie", 60)):
        limpios[campo], err = _texto(datos, campo, maximo)
        limpios[campo] = limpios[campo] or None
        if err:
            errores[campo] = err
    tipo = str(datos.get("tipo") or "").strip()
    if tipo not in TIPOS:
        errores["tipo"] = "Selecciona un tipo de equipo."
    limpios["tipo"] = tipo
    try:
        area_id = int(datos.get("area_id")) if datos.get("area_id") not in (None, "") else None
    except (TypeError, ValueError):
        area_id = -1
    if area_id is not None and not consultar(
            "SELECT id FROM areas WHERE id = %s AND empresa_id = %s", (area_id, g.usuario["empresa_id"]), uno=True):
        errores["area_id"] = "Selecciona un área de tu empresa."
    limpios["area_id"] = area_id
    return limpios, errores


def _codigo_repetido(error):
    return isinstance(error, pymysql.err.IntegrityError) and error.args and error.args[0] == 1062


# =====================================================================
#  Usado por tickets.py al registrar un ticket escaneado
# =====================================================================
def buscar_por_token(token, empresa_id):
    """Devuelve (equipo, mensaje_error, codigo_http)."""
    token = (token or "").strip()
    if not PATRON_TOKEN.match(token):
        return None, "El código QR no es válido: no fue generado por este sistema.", 400
    equipo = consultar(SQL_EQUIPOS + " WHERE q.qr_token = %s", (token,), uno=True)
    if equipo is None:
        return None, ("Este QR no corresponde a ningún equipo registrado. "
                      "Puede ser una etiqueta antigua (QR regenerado) o alterada."), 404
    if equipo["empresa_id"] != empresa_id:
        return None, "Este QR pertenece a un equipo de otra empresa.", 403
    if not equipo["activo"]:
        return None, f"El equipo {equipo['codigo']} fue dado de baja y ya no recibe tickets.", 410
    return equipo, None, 200


def vincular_equipo(cur, ticket_id, token, empresa_id):
    """Guarda en el ticket el equipo escaneado. Si el token no es válido se cancela el registro."""
    equipo, error, _codigo = buscar_por_token(token, empresa_id)
    if error:
        raise ErrorRegla(error)
    cur.execute("UPDATE tickets SET equipo_id = %s WHERE id = %s", (equipo["id"], ticket_id))
    return equipo


# =====================================================================
#  Enlace que va dentro del QR
# =====================================================================
COOKIE_QR = "qr_pendiente"


@equipos_bp.get("/qr/<token>")
def abrir_qr(token):
    """El celular escanea la etiqueta con su cámara normal y abre esta dirección.
    - Con sesión: va directo a Nuevo Ticket con el equipo.
    - Sin sesión: guarda el token 10 minutos en una cookie, pide login y luego vuelve."""
    if not PATRON_TOKEN.match(token or ""):
        return redirect(url_for("pantalla", pagina="nuevo_ticket", equipo="invalido"))
    if g.get("usuario_token"):
        return redirect(url_for("pantalla", pagina="nuevo_ticket", equipo=token))
    respuesta = redirect(url_for("inicio"))
    respuesta.set_cookie(COOKIE_QR, token, max_age=600, httponly=True, samesite="Lax")
    return respuesta


@equipos_bp.after_app_request
def _volver_al_qr_despues_del_login(respuesta):
    """Si alguien escaneó un QR sin sesión, después de iniciar sesión lo lleva al formulario."""
    token = request.cookies.get(COOKIE_QR)
    if not token or request.path != "/" or request.method != "POST":
        return respuesta
    login_ok = respuesta.status_code in (301, 302, 303) and any(
        config.COOKIE_TOKEN + "=" in h for h in respuesta.headers.getlist("Set-Cookie"))
    if login_ok:
        respuesta.headers["Location"] = url_for("pantalla", pagina="nuevo_ticket", equipo=token) \
            if PATRON_TOKEN.match(token) else respuesta.headers["Location"]
        respuesta.delete_cookie(COOKIE_QR)
    return respuesta


# =====================================================================
#  API
# =====================================================================
@equipos_bp.get("/api/equipos")
@login_requerido
def listar_equipos():
    sin_permiso = _solo(ROL_ADMIN, ROL_TECNICO)
    if sin_permiso:
        return sin_permiso
    ver_bajas = request.args.get("bajas") == "1"
    filas = consultar(
        SQL_EQUIPOS + " WHERE q.empresa_id = %s" + ("" if ver_bajas else " AND q.activo = 1")
        + " ORDER BY q.activo DESC, q.codigo",
        (g.usuario["empresa_id"],),
    )
    empresa = consultar("SELECT nombre, prefijo_ticket FROM empresas WHERE id = %s",
                        (g.usuario["empresa_id"],), uno=True)
    return jsonify(
        equipos=[_equipo_json(e) for e in filas],
        tipos=TIPOS,
        areas=consultar("SELECT id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre",
                        (g.usuario["empresa_id"],)),
        empresa={"nombre": empresa["nombre"], "prefijo": empresa["prefijo_ticket"]},
        puede_editar=g.usuario["rol"] == ROL_ADMIN,
    )


@equipos_bp.post("/api/equipos")
@login_requerido
def crear_equipo():
    sin_permiso = _solo(ROL_ADMIN)
    if sin_permiso:
        return sin_permiso
    datos, errores = _validar(request.get_json(silent=True) or {})
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute(
                """INSERT INTO equipos (empresa_id, area_id, codigo, nombre, tipo, marca, modelo, serie, ubicacion, qr_token)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (g.usuario["empresa_id"], datos["area_id"], datos["codigo"], datos["nombre"], datos["tipo"],
                 datos["marca"], datos["modelo"], datos["serie"], datos["ubicacion"], nuevo_token()),
            )
            equipo_id = cur.lastrowid
        con.commit()
    except pymysql.MySQLError as e:
        con.rollback()
        if _codigo_repetido(e):
            return jsonify(error="Ya existe un equipo con ese código.",
                           errores={"codigo": "Ya existe un equipo con ese código."}), 409
        raise
    return jsonify(mensaje=f"Equipo {datos['codigo']} registrado. Ya puedes imprimir su etiqueta QR.",
                   equipo=_equipo_json(_equipo(equipo_id))), 201


@equipos_bp.put("/api/equipos/<int:equipo_id>")
@login_requerido
def editar_equipo(equipo_id):
    sin_permiso = _solo(ROL_ADMIN)
    if sin_permiso:
        return sin_permiso
    if not _equipo(equipo_id):
        return jsonify(error="El equipo no existe."), 404
    datos, errores = _validar(request.get_json(silent=True) or {})
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute(
                """UPDATE equipos SET area_id = %s, codigo = %s, nombre = %s, tipo = %s, marca = %s,
                          modelo = %s, serie = %s, ubicacion = %s, activo = 1
                    WHERE id = %s AND empresa_id = %s""",
                (datos["area_id"], datos["codigo"], datos["nombre"], datos["tipo"], datos["marca"],
                 datos["modelo"], datos["serie"], datos["ubicacion"], equipo_id, g.usuario["empresa_id"]),
            )
        con.commit()
    except pymysql.MySQLError as e:
        con.rollback()
        if _codigo_repetido(e):
            return jsonify(error="Ya existe un equipo con ese código.",
                           errores={"codigo": "Ya existe un equipo con ese código."}), 409
        raise
    return jsonify(mensaje="Equipo actualizado. El QR no cambia: la etiqueta impresa sigue sirviendo.",
                   equipo=_equipo_json(_equipo(equipo_id)))


@equipos_bp.delete("/api/equipos/<int:equipo_id>")
@login_requerido
def dar_de_baja(equipo_id):
    """No se borra: el historial de tickets del equipo se conserva."""
    sin_permiso = _solo(ROL_ADMIN)
    if sin_permiso:
        return sin_permiso
    equipo = _equipo(equipo_id)
    if not equipo:
        return jsonify(error="El equipo no existe."), 404
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE equipos SET activo = 0 WHERE id = %s", (equipo_id,))
    con.commit()
    return jsonify(mensaje=f"Equipo {equipo['codigo']} dado de baja. Su QR ya no permite registrar tickets.")


@equipos_bp.post("/api/equipos/<int:equipo_id>/regenerar-qr")
@login_requerido
def regenerar_qr(equipo_id):
    sin_permiso = _solo(ROL_ADMIN)
    if sin_permiso:
        return sin_permiso
    equipo = _equipo(equipo_id)
    if not equipo:
        return jsonify(error="El equipo no existe."), 404
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE equipos SET qr_token = %s WHERE id = %s", (nuevo_token(), equipo_id))
    con.commit()
    return jsonify(mensaje=f"QR de {equipo['codigo']} regenerado. Imprime la etiqueta nueva: la anterior ya no funciona.",
                   equipo=_equipo_json(_equipo(equipo_id)))


@equipos_bp.get("/api/equipos/qr/<token>")
@login_requerido
def ver_por_qr(token):
    """Lo que ve el usuario al escanear: equipo, ubicación e historial de incidencias."""
    equipo, error, codigo = buscar_por_token(token, g.usuario["empresa_id"])
    if error:
        return jsonify(error=error), codigo
    datos = _equipo_json(equipo, con_qr=False)
    datos["token"] = equipo["qr_token"]
    return jsonify(equipo=datos, historial=_historial(equipo["id"]))


@equipos_bp.get("/api/tickets/<int:ticket_id>/equipo")
@login_requerido
def equipo_del_ticket(ticket_id):
    ticket = Ticket.obtener(ticket_id, g.usuario["empresa_id"])
    if ticket is None or not puede_ver(g.usuario, ticket):
        return jsonify(error="El ticket no existe."), 404
    fila = consultar("SELECT equipo_id FROM tickets WHERE id = %s", (ticket_id,), uno=True)
    if not fila or not fila["equipo_id"]:
        return jsonify(equipo=None)
    equipo = _equipo(fila["equipo_id"])
    historial = [h for h in _historial(equipo["id"], 6) if h["id"] != ticket_id][:5]
    return jsonify(equipo=_equipo_json(equipo, con_qr=False), historial=historial)


# =====================================================================
#  PDF de etiquetas (ReportLab): 2 columnas x 5 filas por hoja A4
# =====================================================================
@equipos_bp.get("/api/equipos/etiquetas.pdf")
@login_requerido
def etiquetas_pdf():
    sin_permiso = _solo(ROL_ADMIN, ROL_TECNICO)
    if sin_permiso:
        return sin_permiso
    ids = [int(x) for x in re.findall(r"\d+", request.args.get("ids", ""))][:200]
    sql = SQL_EQUIPOS + " WHERE q.empresa_id = %s AND q.activo = 1"
    params = [g.usuario["empresa_id"]]
    if ids:
        sql += f" AND q.id IN ({', '.join(['%s'] * len(ids))})"
        params += ids
    equipos = consultar(sql + " ORDER BY q.codigo", params)
    if not equipos:
        return jsonify(error="No hay equipos para imprimir."), 404
    empresa = consultar("SELECT nombre, color_primario FROM empresas WHERE id = %s",
                        (g.usuario["empresa_id"],), uno=True)
    try:
        pdf = _armar_pdf(equipos, empresa)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("No se pudo generar el PDF de etiquetas")
        return jsonify(error="No se pudo generar el PDF de etiquetas."), 500
    nombre = "etiqueta_" + equipos[0]["codigo"] if len(equipos) == 1 else "etiquetas_qr"
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=False,
                     download_name=f"{nombre}.pdf")


def _recortar(texto, fuente, tam, ancho, lienzo):
    texto = texto or ""
    while texto and lienzo.stringWidth(texto, fuente, tam) > ancho:
        texto = texto[:-2] + "…" if len(texto) > 2 else ""
    return texto


def _armar_pdf(equipos, empresa):
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    color = colors.HexColor(empresa["color_primario"] or "#2D6A4F")
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=A4)
    c.setTitle(f"Etiquetas QR - {empresa['nombre']}")
    ancho_hoja, alto_hoja = A4
    columnas, filas = 2, 5
    ancho, alto = 9.2 * cm, 5.0 * cm
    margen_x = (ancho_hoja - columnas * ancho) / 3
    margen_y = (alto_hoja - filas * alto) / (filas + 1)
    lado_qr = 3.9 * cm

    for i, e in enumerate(equipos):
        pos = i % (columnas * filas)
        if i and pos == 0:
            c.showPage()
        col, fila = pos % columnas, pos // columnas
        x = margen_x + col * (ancho + margen_x)
        y = alto_hoja - (fila + 1) * (alto + margen_y)

        # Marco de corte
        c.setStrokeColor(colors.HexColor("#B8C4D6"))
        c.setDash(3, 3)
        c.roundRect(x, y, ancho, alto, 6, stroke=1, fill=0)
        c.setDash()

        # Franja superior con el nombre de la empresa
        c.setFillColor(color)
        c.roundRect(x, y + alto - 0.75 * cm, ancho, 0.75 * cm, 6, stroke=0, fill=1)
        c.rect(x, y + alto - 0.75 * cm, ancho, 0.4 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 0.35 * cm, y + alto - 0.5 * cm, _recortar(f"{empresa['nombre']} · Soporte TI",
                                                                   "Helvetica-Bold", 9, ancho - 0.7 * cm, c))

        # QR con nivel de corrección H (30 %): sigue leyéndose aunque la etiqueta se raye
        widget = QrCodeWidget(enlace_qr(e["qr_token"]), barLevel="H", barBorder=2)
        x1, y1, x2, y2 = widget.getBounds()
        dibujo = Drawing(lado_qr, lado_qr, transform=[lado_qr / (x2 - x1), 0, 0, lado_qr / (y2 - y1), 0, 0])
        dibujo.add(widget)
        renderPDF.draw(dibujo, c, x + 0.15 * cm, y + 0.2 * cm)

        # Datos visibles (impresos, NO dentro del QR)
        tx = x + lado_qr + 0.3 * cm
        libre = ancho - lado_qr - 0.55 * cm
        c.setFillColor(colors.HexColor("#0F2A47"))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(tx, y + alto - 1.45 * cm, _recortar(e["codigo"], "Helvetica-Bold", 13, libre, c))
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(tx, y + alto - 2.0 * cm, _recortar(e["nombre"], "Helvetica-Bold", 8.5, libre, c))
        c.setFillColor(colors.HexColor("#47617F"))
        c.setFont("Helvetica", 7.5)
        c.drawString(tx, y + alto - 2.45 * cm, _recortar(e["tipo"] + (f" · {e['marca']}" if e["marca"] else ""),
                                                         "Helvetica", 7.5, libre, c))
        c.drawString(tx, y + alto - 2.85 * cm, _recortar(e["ubicacion"], "Helvetica", 7.5, libre, c))

        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(tx, y + 0.85 * cm, "¿Falla este equipo?")
        c.setFont("Helvetica", 7)
        c.drawString(tx, y + 0.45 * cm, "Escanea el QR para reportarlo")

    c.save()
    return salida.getvalue()
