import os
import json
from db import obtener_conexion
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv

load_dotenv()

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": "mailto:soporte@mesadeayuda.pe"}

def enviar_webpush(endpoint, p256dh, auth, titulo, cuerpo, url):
    if not VAPID_PRIVATE_KEY: return
    try:
        payload = json.dumps({"title": titulo, "body": cuerpo, "url": url})
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=dict(VAPID_CLAIMS)
        )
    except WebPushException as e:
        print("Error Push:", e)

def revisar_tickets_cron():
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            # 1. Buscar todos los tickets activos con SLA
            cur.execute("""
                SELECT t.id, t.empresa_id, t.numero, t.asunto, t.estado, t.prioridad_id,
                       t.tecnico_id, t.alerta_sla_enviada, t.escalado_sla,
                       t.created_at, t.fecha_limite, e.prefijo_ticket, p.sla_horas
                FROM tickets t
                JOIN empresas e ON e.id = t.empresa_id
                JOIN prioridades p ON p.id = t.prioridad_id
                WHERE t.estado IN ('Abierto', 'En proceso') AND t.fecha_limite IS NOT NULL
            """)
            tickets = cur.fetchall()

            for t in tickets:
                codigo = f"{t['prefijo_ticket']}-{t['numero']:04d}"
                # Lógica simplificada de horas
                cur.execute("""
                    SELECT TIMESTAMPDIFF(MINUTE, %s, NOW()) AS transcurridos,
                           TIMESTAMPDIFF(MINUTE, NOW(), %s) AS restantes,
                           TIMESTAMPDIFF(MINUTE, %s, %s) AS plazo_total
                """, (t["created_at"], t["fecha_limite"], t["created_at"], t["fecha_limite"]))
                tiempos = cur.fetchone()
                restantes = tiempos["restantes"] if tiempos["restantes"] is not None else 0
                transcurridos = tiempos["transcurridos"] or 0
                plazo_total = max(tiempos["plazo_total"] or (t["sla_horas"] * 60), 1)

                cur.execute(
                    "SELECT id FROM users WHERE empresa_id = %s AND rol = 'Administrador' AND activo = 1",
                    (t["empresa_id"],)
                )
                destinatarios = {r["id"] for r in cur.fetchall()}
                if t["tecnico_id"]:
                    destinatarios.add(t["tecnico_id"])

                # 1. Vencido -> Escalamiento automático
                if restantes < 0 and not t["escalado_sla"]:
                    nueva_prio = 1 if t["prioridad_id"] != 1 else t["prioridad_id"]
                    cur.execute("""
                        UPDATE tickets
                           SET escalado_sla = 1, alerta_sla_enviada = 1,
                               fecha_escalamiento = NOW(), prioridad_id = %s
                         WHERE id = %s
                    """, (nueva_prio, t["id"]))
                    titulo = f"🚨 SLA Vencido y Escalado: {codigo}"
                    cuerpo = f"{t['asunto']} superó el tiempo límite y fue escalado."
                    for uid in destinatarios:
                        cur.execute(
                            "INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje) VALUES (%s, 'SLA', %s, %s, %s)",
                            (uid, t["id"], titulo[:150], cuerpo[:255])
                        )
                        cur.execute("SELECT endpoint, p256dh, auth FROM push_suscripciones WHERE usuario_id = %s AND activo = 1", (uid,))
                        for sub in cur.fetchall():
                            enviar_webpush(sub["endpoint"], sub["p256dh"], sub["auth"], titulo, cuerpo, f"/detalle_ticket?id={t['id']}")

                # 2. Por vencer (>= 75% del plazo) -> Alerta preventiva
                elif restantes >= 0 and transcurridos >= (plazo_total * 0.75) and not t["alerta_sla_enviada"]:
                    cur.execute("UPDATE tickets SET alerta_sla_enviada = 1 WHERE id = %s", (t["id"],))
                    titulo = f"⚠️ SLA por vencer: {codigo}"
                    cuerpo = f"Quedan {restantes} min para {t['asunto']}."
                    for uid in destinatarios:
                        cur.execute(
                            "INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje) VALUES (%s, 'SLA', %s, %s, %s)",
                            (uid, t["id"], titulo[:150], cuerpo[:255])
                        )
                        cur.execute("SELECT endpoint, p256dh, auth FROM push_suscripciones WHERE usuario_id = %s AND activo = 1", (uid,))
                        for sub in cur.fetchall():
                            enviar_webpush(sub["endpoint"], sub["p256dh"], sub["auth"], titulo, cuerpo, f"/detalle_ticket?id={t['id']}")
            con.commit()
    finally:
        con.close()
    print("Revisión de SLA en background terminada.")

if __name__ == "__main__":
    revisar_tickets_cron()