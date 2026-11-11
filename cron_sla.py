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
                SELECT t.id, t.numero, t.asunto, t.estado, t.alerta_sla_enviada, t.escalado_sla,
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
                cur.execute("SELECT TIMESTAMPDIFF(MINUTE, NOW(), %s) AS restantes", (t["fecha_limite"],))
                restantes = cur.fetchone()["restantes"] or 0

                # Ejemplo 75% (aviso)
                if restantes >= 0 and restantes <= (t["sla_horas"] * 60 * 0.25) and not t["alerta_sla_enviada"]:
                    cur.execute("UPDATE tickets SET alerta_sla_enviada = 1 WHERE id = %s", (t["id"],))

                    # Buscar suscripciones de admins y enviar Push nativo real
                    cur.execute("""
                        SELECT p.endpoint, p.p256dh, p.auth FROM push_suscripciones p
                        JOIN users u ON u.id = p.usuario_id WHERE u.rol = 'Administrador' AND p.activo = 1
                    """)
                    for sub in cur.fetchall():
                        enviar_webpush(sub["endpoint"], sub["p256dh"], sub["auth"],
                                       f"⚠️ SLA por vencer: {codigo}",
                                       f"Quedan {restantes} min para {t['asunto']}.",
                                       f"/detalle_ticket?id={t['id']}")
            con.commit()
    finally:
        con.close()
    print("Revisión de SLA en background terminada.")

if __name__ == "__main__":
    revisar_tickets_cron()