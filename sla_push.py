"""
MÓDULO 7 — Alertas Web Push de SLA y Escalamiento Automático.
"""

import json
import os
from flask import Blueprint, g, jsonify, request, send_from_directory
from auth import (
    ROL_ADMIN,
    ROL_TECNICO,
    empresa_actual,
    login_requerido,
    roles_requeridos,
)
from db import conexion

sla_push_bp = Blueprint("sla_push", __name__)

VAPID_PUBLIC_KEY = os.getenv(
    "VAPID_PUBLIC_KEY",
    "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U",
)
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:soporte@mesadeayuda.pe"}


@sla_push_bp.get("/sw.js")
def service_worker():
    """Sirve el Service Worker desde la raíz para que tenga alcance en toda la app."""
    return send_from_directory("static/js", "sw.js", mimetype="application/javascript")


@sla_push_bp.get("/api/push/vapid-public-key")
@login_requerido
def obtener_vapid_key():
    return jsonify(publicKey=VAPID_PUBLIC_KEY)


@sla_push_bp.post("/api/push/suscribir")
@login_requerido
def suscribir_push():
    """Guarda la suscripción del navegador en la tabla push_suscripciones."""
    datos = request.get_json(silent=True) or {}
    endpoint = datos.get("endpoint")
    keys = datos.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth_key = keys.get("auth")

    if not endpoint or not p256dh or not auth_key:
        return jsonify(ok=False, error="Datos de suscripción incompletos."), 400

    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO push_suscripciones (usuario_id, endpoint, p256dh, auth, user_agent, activo)
               VALUES (%s, %s, %s, %s, %s, 1)
               ON DUPLICATE KEY UPDATE
                   usuario_id = VALUES(usuario_id),
                   p256dh = VALUES(p256dh),
                   auth = VALUES(auth),
                   activo = 1""",
            (
                g.usuario["id"],
                endpoint,
                p256dh,
                auth_key,
                request.headers.get("User-Agent", "")[:255],
            ),
        )
    con.commit()
    return jsonify(ok=True, mensaje="Notificaciones Push activadas en este navegador.")


def _enviar_webpush_usuario(cur, usuario_id, titulo, cuerpo, url="/sla"):
    """Envía Web Push real si hay VAPID_PRIVATE_KEY configurada."""
    cur.execute(
        "SELECT id, endpoint, p256dh, auth FROM push_suscripciones WHERE usuario_id = %s AND activo = 1",
        (usuario_id,),
    )
    suscripciones = cur.fetchall()
    if not suscripciones or not VAPID_PRIVATE_KEY:
        return 0

    enviados = 0
    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({"title": titulo, "body": cuerpo, "url": url})
        for sub in suscripciones:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS,
                )
                enviados += 1
            except WebPushException:
                cur.execute(
                    "UPDATE push_suscripciones SET activo = 0 WHERE id = %s",
                    (sub["id"],),
                )
    except ImportError:
        pass
    return enviados


@sla_push_bp.post("/api/sla/verificar-alertas")
@roles_requeridos(ROL_ADMIN, ROL_TECNICO)
def verificar_y_escalar_sla():
    """
    Revisa los tickets activos de la empresa:
    1) Si han consumido >= 75% de su tiempo SLA (Por vencer) y no tienen alerta_sla_enviada,
       crea notificación tipo 'SLA' y envía Web Push.
    2) Si ya superaron la fecha_limite (Vencidos) y no tienen escalado_sla = 1,
       los escala automáticamente a prioridad Alta (1) y registra en el historial.
    """
    empresa_id = empresa_actual()
    con = conexion()
    alertados = []
    escalados = []

    with con.cursor() as cur:
        cur.execute(
            """SELECT t.id, t.numero, t.asunto, t.estado, t.prioridad_id, t.tecnico_id,
                      t.alerta_sla_enviada, t.escalado_sla, t.created_at, t.fecha_limite,
                      p.nombre AS prioridad, p.sla_horas, e.prefijo_ticket
                 FROM tickets t
                 JOIN prioridades p ON p.id = t.prioridad_id
                 JOIN empresas e ON e.id = t.empresa_id
                WHERE t.empresa_id = %s
                  AND t.estado IN ('Abierto', 'En proceso')
                  AND t.fecha_limite IS NOT NULL""",
            (empresa_id,),
        )
        tickets_activos = cur.fetchall()

        cur.execute(
            "SELECT id FROM users WHERE empresa_id = %s AND rol = %s AND activo = 1",
            (empresa_id, ROL_ADMIN),
        )
        admins_ids = {f["id"] for f in cur.fetchall()}

        for t in tickets_activos:
            codigo = f"{t['prefijo_ticket']}-{t['numero']:04d}"
            cur.execute(
                """SELECT TIMESTAMPDIFF(MINUTE, %s, NOW()) AS transcurridos,
                          TIMESTAMPDIFF(MINUTE, NOW(), %s) AS restantes""",
                (t["created_at"], t["fecha_limite"]),
            )
            tiempos = cur.fetchone()
            restantes = tiempos["restantes"] or 0
            transcurridos = tiempos["transcurridos"] or 0
            umbral_amarillo = t["sla_horas"] * 60 * 0.75

            destinatarios = set(admins_ids)
            if t["tecnico_id"]:
                destinatarios.add(t["tecnico_id"])

            # CASO 1: TICKET VENCIDO -> Escalamiento automático
            if restantes < 0 and not t["escalado_sla"]:
                nueva_prio = 1 if t["prioridad_id"] != 1 else t["prioridad_id"]
                cur.execute(
                    """UPDATE tickets
                          SET escalado_sla = 1,
                              alerta_sla_enviada = 1,
                              fecha_escalamiento = NOW(),
                              prioridad_id = %s
                        WHERE id = %s""",
                    (nueva_prio, t["id"]),
                )
                comentario_esc = (
                    f"Escalamiento automático por SLA vencido. Prioridad elevada a Alta."
                    if t["prioridad_id"] != 1
                    else "Escalamiento automático por SLA vencido (Ticket ya en prioridad Alta)."
                )
                cur.execute(
                    """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                       VALUES (%s, %s, 'COMENTARIO', %s, NOW())""",
                    (t["id"], g.usuario["id"], comentario_esc),
                )
                titulo = f"🚨 SLA Vencido y Escalado: {codigo}"
                mensaje = f"{t['asunto']} superó el tiempo límite. {comentario_esc}"
                for uid in destinatarios:
                    cur.execute(
                        """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                           VALUES (%s, 'SLA', %s, %s, %s)""",
                        (uid, t["id"], titulo[:150], mensaje[:255]),
                    )
                    _enviar_webpush_usuario(
                        cur, uid, titulo, mensaje, f"/detalle_ticket?id={t['id']}"
                    )
                escalados.append(
                    {"id": t["id"], "codigo": codigo, "asunto": t["asunto"]}
                )

            # CASO 2: TICKET POR VENCER (>= 75% del plazo) -> Alerta preventiva
            elif (
                restantes >= 0
                and transcurridos >= umbral_amarillo
                and not t["alerta_sla_enviada"]
            ):
                cur.execute(
                    "UPDATE tickets SET alerta_sla_enviada = 1 WHERE id = %s",
                    (t["id"],),
                )
                titulo = f"⚠️ SLA por vencer: {codigo}"
                mensaje = f"Quedan {restantes} min para resolver «{t['asunto']}»."
                for uid in destinatarios:
                    cur.execute(
                        """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                           VALUES (%s, 'SLA', %s, %s, %s)""",
                        (uid, t["id"], titulo[:150], mensaje[:255]),
                    )
                    _enviar_webpush_usuario(
                        cur, uid, titulo, mensaje, f"/detalle_ticket?id={t['id']}"
                    )
                alertados.append(
                    {
                        "id": t["id"],
                        "codigo": codigo,
                        "asunto": t["asunto"],
                        "restantes": restantes,
                    }
                )

    con.commit()
    return jsonify(
        ok=True,
        alertados=alertados,
        escalados=escalados,
        mensaje=f"Verificación completada: {len(alertados)} alerta(s) preventiva(s) y {len(escalados)} escalamiento(s).",
    )
