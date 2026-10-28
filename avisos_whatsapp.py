"""
MÓDULO 4 (avance 2) — Aviso al técnico por WhatsApp / SMS con Vonage (Messages API)
=================================================================================

Cuándo se envía:  cada vez que un ticket se ASIGNA o REASIGNA a un técnico
                  (pantalla Asignación, panel del detalle del ticket o API de Postman).
Qué se envía:     código del ticket, prioridad, asunto y enlace al detalle.
Qué se registra:  cada mensaje en la tabla mensajes_externos con su estado:
                  PENDIENTE → ENVIADO → ENTREGADO → LEIDO   (o FALLIDO + motivo)

Cómo funciona Vonage (Messages API):
  1. Nuestro servidor hace un POST HTTPS a Vonage con el número, el canal y el texto.
     Se autentica con API key + API secret (Basic Auth). Las claves están en .env.
  2. Vonage responde 202 (aceptado) con un "message_uuid" (el id del mensaje).
  3. Más tarde Vonage nos llama a NOSOTROS (webhook de estado) para contarnos si el
     mensaje fue entregado, leído o rechazado. Con el message_uuid actualizamos la fila.

Variables de entorno (.env) — nunca en el código ni en GitHub:
  VONAGE_API_KEY, VONAGE_API_SECRET   claves del panel de Vonage
  VONAGE_CANAL=whatsapp               whatsapp | sms
  VONAGE_SANDBOX=1                    1 = Messages API Sandbox (gratis, para pruebas)
  VONAGE_WHATSAPP_FROM=14157386102    número del Sandbox de WhatsApp
  VONAGE_SMS_FROM=MesaTI              remitente para SMS (solo canal sms)
  VONAGE_WEBHOOK_TOKEN=...            clave para que solo Vonage pueda llamar al webhook
  APP_URL_PUBLICA=https://...         dirección pública del sistema (para el enlace)
"""
import base64
import hmac
import json
import os
import re
import urllib.error
import urllib.request

from flask import Blueprint, current_app, g, jsonify, request

import config  # noqa: F401  (carga el archivo .env)
from db import conexion, consultar
from tickets import ROL_ADMIN, login_requerido
from vistas import V_TICKETS

avisos_bp = Blueprint("avisos_whatsapp", __name__)

URL_SANDBOX = "https://messages-sandbox.nexmo.com/v1/messages"
URL_PRODUCCION = "https://api.nexmo.com/v1/messages"
TIEMPO_ESPERA = 10  # segundos máximos esperando a Vonage (no se cuelga la asignación)

# Estado que informa Vonage en el webhook  →  estado en nuestra tabla
ESTADOS_VONAGE = {
    "submitted": "ENVIADO",
    "delivered": "ENTREGADO",
    "read": "LEIDO",
    "rejected": "FALLIDO",
    "undeliverable": "FALLIDO",
}
ORDEN_ESTADOS = {"PENDIENTE": 0, "ENVIADO": 1, "ENTREGADO": 2, "LEIDO": 3}


# =====================================================================
#  Configuración
# =====================================================================
def _cfg():
    canal = (os.getenv("VONAGE_CANAL") or "whatsapp").strip().lower()
    sandbox = (os.getenv("VONAGE_SANDBOX") or "1").strip() not in ("0", "false", "no")
    return {
        "api_key": (os.getenv("VONAGE_API_KEY") or "").strip(),
        "api_secret": (os.getenv("VONAGE_API_SECRET") or "").strip(),
        "canal": "sms" if canal == "sms" else "whatsapp",
        # VONAGE_URL solo se usa para pruebas locales (simulador); normalmente queda vacío
        "url": (os.getenv("VONAGE_URL") or "").strip()
        or (URL_SANDBOX if sandbox and canal != "sms" else URL_PRODUCCION),
        "from_whatsapp": (os.getenv("VONAGE_WHATSAPP_FROM") or "14157386102").strip(),
        "from_sms": (os.getenv("VONAGE_SMS_FROM") or "MesaTI").strip(),
        "webhook_token": (os.getenv("VONAGE_WEBHOOK_TOKEN") or "").strip(),
        "app_url": (os.getenv("APP_URL_PUBLICA") or "").strip().rstrip("/"),
    }


def vonage_configurado():
    c = _cfg()
    return bool(c["api_key"] and c["api_secret"])


# =====================================================================
#  Número de teléfono
# =====================================================================
def normalizar_telefono(texto):
    """Convierte lo que escribe el usuario al formato que pide Vonage: E.164 SIN '+'.

    '987 654 321' → '51987654321'  (celular peruano: 9 dígitos que empiezan en 9)
    '+51 987654321' → '51987654321'
    Devuelve (numero, error). Si el texto está vacío devuelve (None, None) = borrar número.
    """
    crudo = (texto or "").strip()
    if not crudo:
        return None, None
    digitos = re.sub(r"[\s\-().]", "", crudo)
    if digitos.startswith("+"):
        digitos = digitos[1:]
    elif digitos.startswith("00"):
        digitos = digitos[2:]
    if not digitos.isdigit():
        return None, "Escribe solo números (puedes empezar con +51)."
    if len(digitos) == 9 and digitos.startswith("9"):
        digitos = "51" + digitos
    if digitos.startswith("51") and not (len(digitos) == 11 and digitos[2] == "9"):
        return None, "Un celular de Perú tiene 9 dígitos y empieza con 9 (ej. 987654321)."
    if not 10 <= len(digitos) <= 15:
        return None, "El número debe tener entre 10 y 15 dígitos con el código de país."
    return digitos, None


def ocultar_telefono(numero):
    """51987654321 → +51 ••• ••• 321 (para mostrarlo en listas sin exponerlo completo)."""
    if not numero:
        return None
    return f"+{numero[:2]} ••• ••• {numero[-3:]}"


# =====================================================================
#  Llamada a la API de Vonage
# =====================================================================
def _llamar_vonage(numero, texto, referencia):
    """Hace el POST a Vonage. Devuelve (message_uuid, None) o (None, motivo_del_error)."""
    c = _cfg()
    if not (c["api_key"] and c["api_secret"]):
        return None, "Vonage no está configurado: faltan VONAGE_API_KEY y VONAGE_API_SECRET en el archivo .env."

    cuerpo = {
        "to": numero,
        "from": c["from_sms"] if c["canal"] == "sms" else c["from_whatsapp"],
        "channel": c["canal"],
        "message_type": "text",
        "text": texto,
        "client_ref": referencia[:40],  # Vonage lo devuelve en el webhook
    }
    credenciales = base64.b64encode(f"{c['api_key']}:{c['api_secret']}".encode()).decode()
    peticion = urllib.request.Request(
        c["url"],
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Basic {credenciales}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as resp:
            datos = json.loads(resp.read().decode("utf-8") or "{}")
            uuid = datos.get("message_uuid")
            return (uuid, None) if uuid else (None, "Vonage no devolvió el id del mensaje.")
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            detalle = {}
        motivo = detalle.get("detail") or detalle.get("title") or e.reason
        if e.code == 401:
            motivo = "Credenciales de Vonage incorrectas (revisa VONAGE_API_KEY y VONAGE_API_SECRET)."
        elif e.code == 429:
            motivo = "Se superó el límite del Sandbox (1 mensaje por segundo / 100 al mes)."
        return None, f"Vonage {e.code}: {motivo}"[:255]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        razon = getattr(e, "reason", e)
        return None, f"No se pudo conectar con Vonage: {razon}"[:255]


# =====================================================================
#  Registro en la tabla mensajes_externos
# =====================================================================
def _registrar(empresa_id, ticket_id, tecnico_id, enviado_por, motivo, telefono, texto):
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO mensajes_externos
                      (empresa_id, ticket_id, tecnico_id, enviado_por, canal, motivo, telefono, mensaje, estado)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDIENTE')""",
            (empresa_id, ticket_id, tecnico_id, enviado_por, _cfg()["canal"].upper(), motivo, telefono, texto[:600]),
        )
        mensaje_id = cur.lastrowid
    con.commit()
    return mensaje_id


def _marcar(mensaje_id, estado, proveedor_id=None, error=None, sumar_intento=False):
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            f"""UPDATE mensajes_externos
                   SET estado = %s, proveedor_id = COALESCE(%s, proveedor_id), error_detalle = %s
                       {', intentos = intentos + 1' if sumar_intento else ''}
                 WHERE id = %s""",
            (estado, proveedor_id, error, mensaje_id),
        )
    con.commit()


def _enviar_y_registrar(mensaje_id, telefono, texto, referencia):
    """Envía un mensaje ya registrado y actualiza su estado. Devuelve el resumen para la interfaz."""
    if not telefono:
        error = "El técnico no tiene número de WhatsApp registrado en «Mi Perfil»."
        _marcar(mensaje_id, "FALLIDO", error=error)
        return {"id": mensaje_id, "estado": "FALLIDO", "error": error}
    uuid, error = _llamar_vonage(telefono, texto, referencia)
    if error:
        _marcar(mensaje_id, "FALLIDO", error=error)
        current_app.logger.warning("Aviso WhatsApp %s falló: %s", mensaje_id, error)
        return {"id": mensaje_id, "estado": "FALLIDO", "error": error}
    _marcar(mensaje_id, "ENVIADO", proveedor_id=uuid)
    return {"id": mensaje_id, "estado": "ENVIADO", "error": None}


# =====================================================================
#  Texto del mensaje
# =====================================================================
def _enlace_ticket(ticket_id):
    base = _cfg()["app_url"]
    try:
        actual = request.host_url.rstrip("/")
    except RuntimeError:
        actual = ""
    # Una dirección local (127.0.0.1, 192.168.x.x, 10.x.x.x) cambia con cada red:
    # se usa la dirección con la que se abrió el sistema. Un dominio real (PythonAnywhere) se respeta.
    local = re.compile(r"^https?://(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
                       r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?(/|$)")
    if actual and (not base or local.match(base)):
        base = actual
    return f"{base}/detalle_ticket?id={ticket_id}"


def armar_texto(ticket, tecnico, reasignacion):
    primer_nombre = (tecnico["nombre"] or "").split()[0] if tecnico.get("nombre") else ""
    accion = "te reasignaron" if reasignacion else "te asignaron"
    return (
        f"*MesaTI – {ticket['empresa']}*\n"
        f"Hola {primer_nombre}, {accion} el ticket *{ticket['codigo']}* (prioridad {ticket['prioridad']}).\n"
        f"{ticket['asunto']}\n"
        f"Revísalo aquí: {_enlace_ticket(ticket['id'])}"
    )


# =====================================================================
#  Punto de entrada que usa tickets.py al asignar / reasignar
# =====================================================================
def avisar_asignacion(ticket_id, tecnico_id, reasignacion, empresa_id, enviado_por=None):
    """Se llama DESPUÉS del commit de la asignación. Nunca lanza excepción:
    si WhatsApp falla, la asignación ya quedó guardada y el error se registra."""
    try:
        ticket = consultar(
            f"SELECT v.id, v.codigo, v.asunto, v.prioridad, v.empresa FROM {V_TICKETS} AS v "
            "WHERE v.id = %s AND v.empresa_id = %s",
            (ticket_id, empresa_id), uno=True)
        tecnico = consultar("SELECT id, nombre, telefono FROM users WHERE id = %s AND empresa_id = %s",
                            (tecnico_id, empresa_id), uno=True)
        if not ticket or not tecnico:
            return None
        texto = armar_texto(ticket, tecnico, reasignacion)
        mensaje_id = _registrar(empresa_id, ticket_id, tecnico_id, enviado_por,
                                "REASIGNACION" if reasignacion else "ASIGNACION", tecnico["telefono"], texto)
        resultado = _enviar_y_registrar(mensaje_id, tecnico["telefono"], texto, f"ticket-{ticket_id}")
        resultado["tecnico"] = tecnico["nombre"]
        return resultado
    except Exception:  # noqa: BLE001  el aviso nunca debe romper la asignación
        current_app.logger.exception("Error al enviar el aviso de asignación por WhatsApp")
        return {"estado": "FALLIDO", "error": "Error interno al enviar el aviso."}


# =====================================================================
#  API: número del usuario en "Mi Perfil"
# =====================================================================
@avisos_bp.get("/api/mi-whatsapp")
@login_requerido
def ver_mi_whatsapp():
    fila = consultar("SELECT telefono FROM users WHERE id = %s", (g.usuario["id"],), uno=True)
    numero = fila["telefono"] if fila else None
    c = _cfg()
    return jsonify(
        telefono=numero,
        telefono_visible=f"+{numero}" if numero else None,
        canal=c["canal"],
        sandbox=c["url"] == URL_SANDBOX,
        numero_sandbox=f"+{c['from_whatsapp']}",
        configurado=vonage_configurado(),
    )


@avisos_bp.put("/api/mi-whatsapp")
@login_requerido
def guardar_mi_whatsapp():
    datos = request.get_json(silent=True) or request.form
    numero, error = normalizar_telefono(datos.get("telefono"))
    if error:
        return jsonify(error=error), 400
    con = conexion()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET telefono = %s WHERE id = %s", (numero, g.usuario["id"]))
    con.commit()
    return jsonify(
        mensaje="Número guardado. Te llegarán los avisos de tickets asignados." if numero
        else "Número eliminado. Ya no recibirás avisos por WhatsApp.",
        telefono=numero, telefono_visible=f"+{numero}" if numero else None,
    )


@avisos_bp.post("/api/mi-whatsapp/prueba")
@login_requerido
def probar_mi_whatsapp():
    """Envía un mensaje de prueba al propio usuario (para verificar que todo funciona)."""
    usuario = consultar("SELECT id, nombre, telefono, empresa_id FROM users WHERE id = %s",
                        (g.usuario["id"],), uno=True)
    if not usuario["telefono"]:
        return jsonify(error="Primero guarda tu número de WhatsApp."), 400
    texto = (f"*MesaTI – {g.usuario.get('empresa') or 'Soporte TI'}*\n"
             f"Hola {usuario['nombre'].split()[0]}, este es un mensaje de prueba. "
             "Si lo recibes, los avisos de tickets asignados te llegarán aquí. ✅")
    mensaje_id = _registrar(g.usuario["empresa_id"], None, usuario["id"], usuario["id"], "PRUEBA",
                            usuario["telefono"], texto)
    resultado = _enviar_y_registrar(mensaje_id, usuario["telefono"], texto, f"prueba-{usuario['id']}")
    if resultado["estado"] == "FALLIDO":
        return jsonify(error=resultado["error"], aviso=resultado), 502
    return jsonify(mensaje="Mensaje de prueba enviado. Revisa tu WhatsApp.", aviso=resultado)


# =====================================================================
#  API: registro de mensajes (pantalla Asignación, solo administrador)
# =====================================================================
def _solo_admin():
    if g.usuario["rol"] != ROL_ADMIN:
        return jsonify(error="Solo el administrador puede ver el registro de avisos."), 403
    return None


@avisos_bp.get("/api/avisos")
@login_requerido
def listar_avisos():
    denegado = _solo_admin()
    if denegado:
        return denegado
    try:
        limite = max(1, min(int(request.args.get("limite", 15)), 100))
    except ValueError:
        limite = 15
    filas = consultar(
        f"""SELECT m.id, m.ticket_id, v.codigo, m.tecnico_id, u.nombre AS tecnico, m.canal, m.motivo,
                   m.telefono, m.estado, m.error_detalle, m.intentos, m.created_at, m.updated_at
              FROM mensajes_externos m
              JOIN users u ON u.id = m.tecnico_id
              LEFT JOIN {V_TICKETS} v ON v.id = m.ticket_id
             WHERE m.empresa_id = %s
             ORDER BY m.created_at DESC, m.id DESC
             LIMIT %s""",
        (g.usuario["empresa_id"], limite))
    resumen = consultar(
        """SELECT SUM(estado IN ('ENVIADO','ENTREGADO','LEIDO')) AS enviados,
                  SUM(estado = 'FALLIDO') AS fallidos, COUNT(*) AS total
             FROM mensajes_externos WHERE empresa_id = %s""",
        (g.usuario["empresa_id"],), uno=True)
    for f in filas:
        f["telefono"] = ocultar_telefono(f["telefono"])
        f["created_at"] = f["created_at"].isoformat(timespec="seconds") if f["created_at"] else None
        f["updated_at"] = f["updated_at"].isoformat(timespec="seconds") if f["updated_at"] else None
    return jsonify(
        avisos=filas,
        resumen={k: int(resumen[k] or 0) for k in ("enviados", "fallidos", "total")},
        configurado=vonage_configurado(),
        canal=_cfg()["canal"],
    )


@avisos_bp.post("/api/avisos/<int:mensaje_id>/reintentar")
@login_requerido
def reintentar_aviso(mensaje_id):
    denegado = _solo_admin()
    if denegado:
        return denegado
    fila = consultar(
        """SELECT m.id, m.ticket_id, m.tecnico_id, m.estado, m.mensaje, u.telefono
             FROM mensajes_externos m JOIN users u ON u.id = m.tecnico_id
            WHERE m.id = %s AND m.empresa_id = %s""",
        (mensaje_id, g.usuario["empresa_id"]), uno=True)
    if not fila:
        return jsonify(error="El aviso no existe."), 404
    if fila["estado"] != "FALLIDO":
        return jsonify(error="Solo se pueden reintentar los avisos fallidos."), 400
    con = conexion()
    with con.cursor() as cur:  # se usa el número ACTUAL del técnico (pudo corregirlo en su perfil)
        cur.execute("UPDATE mensajes_externos SET telefono = %s, estado = 'PENDIENTE', intentos = intentos + 1 "
                    "WHERE id = %s", (fila["telefono"], mensaje_id))
    con.commit()
    resultado = _enviar_y_registrar(mensaje_id, fila["telefono"], fila["mensaje"], f"ticket-{fila['ticket_id']}")
    if resultado["estado"] == "FALLIDO":
        return jsonify(error=resultado["error"], aviso=resultado), 502
    return jsonify(mensaje="Aviso reenviado.", aviso=resultado)


# =====================================================================
#  WEBHOOK DE ESTADO: Vonage nos avisa si el mensaje se entregó / leyó / falló
#  URL que se configura en Vonage (Messages API Sandbox → Webhooks → Status):
#     https://TU-DOMINIO/webhooks/vonage/estado?token=EL_VALOR_DE_VONAGE_WEBHOOK_TOKEN
#  No usa login (lo llama Vonage, no un usuario); por eso se protege con el token.
# =====================================================================
def _token_valido():
    esperado = _cfg()["webhook_token"]
    recibido = request.args.get("token", "")
    return bool(esperado) and hmac.compare_digest(esperado, recibido)


@avisos_bp.post("/webhooks/vonage/estado")
def webhook_estado():
    if not _token_valido():
        return jsonify(error="token inválido"), 401
    datos = request.get_json(silent=True) or {}
    uuid = datos.get("message_uuid")
    estado = ESTADOS_VONAGE.get((datos.get("status") or "").lower())
    if not uuid or not estado:
        return "", 204  # algo que no nos interesa: respondemos OK para que Vonage no reintente
    error = None
    if estado == "FALLIDO":
        e = datos.get("error") or {}
        error = (f"Vonage: {e.get('title', '')} {e.get('detail', '')}".strip() or "Vonage rechazó el mensaje.")[:255]
    fila = consultar("SELECT id, estado FROM mensajes_externos WHERE proveedor_id = %s", (uuid,), uno=True)
    if fila:
        # Los webhooks pueden llegar desordenados: nunca retrocedemos (LEIDO no vuelve a ENTREGADO)
        if estado == "FALLIDO" or ORDEN_ESTADOS.get(estado, 0) > ORDEN_ESTADOS.get(fila["estado"], -1):
            _marcar(fila["id"], estado, error=error)
    return "", 200


@avisos_bp.post("/webhooks/vonage/entrante")
def webhook_entrante():
    """Mensajes que el técnico escribe al número del Sandbox. Solo respondemos 200
    (si respondiéramos error, Vonage reintentaría durante 24 horas)."""
    if not _token_valido():
        return jsonify(error="token inválido"), 401
    return "", 200
