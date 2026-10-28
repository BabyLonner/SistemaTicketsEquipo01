from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from db import obtener_conexion

def evaluar_sla_ticket(ticket):
    """
    Calcula el estado del SLA para mostrar el semáforo visual en el frontend.
    Retorna la clase CSS, el texto y el estado correspondiente.
    """
    estado_actual = ticket.get('estado')
    
    # Si el ticket ya fue resuelto o cerrado, el SLA se congela como completado
    if estado_actual in ['Resuelto', 'Cerrado']:
        return {
            "clase": "sla-cumplido", 
            "texto": "Completado", 
            "badge_class": "status-resolved"
        }
    
    created_at = ticket.get('created_at')
    fecha_limite = ticket.get('fecha_limite')
    
    if not created_at or not fecha_limite:
        return {"clase": "sla-normal", "texto": "Sin SLA", "badge_class": ""}

    ahora = datetime.now()
    
    # Si ya pasó la fecha límite -> Vencido (Rojo)
    if ahora > fecha_limite:
        return {
            "clase": "sla-vencido", 
            "texto": "Vencido", 
            "badge_class": "priority-high"
        }
    
    # Cálculo del porcentaje de tiempo transcurrido
    total_duracion = (fecha_limite - created_at).total_seconds()
    transcurrido = (ahora - created_at).total_seconds()
    
    porcentaje = (transcurrido / total_duracion) * 100 if total_duracion > 0 else 100

    # Lógica del semáforo: Si supera el 80% del tiempo -> Por vencer (Amarillo/Naranja)
    if porcentaje >= 80:
        return {
            "clase": "sla-por-vencer", 
            "texto": "Por vencer", 
            "badge_class": "priority-medium"
        }
    else:
        return {
            "clase": "sla-en-tiempo", 
            "texto": "En tiempo", 
            "badge_class": "priority-low"
        }


def tarea_escalamiento_automatico():
    """
    Funcionalidad de Investigación - Módulo 7 (Escalamiento automático por cron):
    Proceso de fondo que revisa periódicamente los tickets vencidos, los escala,
    registra el historial y notifica automáticamente al supervisor/administrador.
    """
    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            # 1. Buscar tickets abiertos o en proceso cuya fecha límite expiró y no han sido escalados
            cursor.execute("""
                SELECT id, empresa_id, codigo, asunto 
                FROM tickets 
                WHERE estado IN ('Abierto', 'En proceso') 
                  AND fecha_limite < NOW() 
                  AND (escalado = 0 OR escalado IS NULL)
            """)
            vencidos = cursor.fetchall()

            for ticket in vencidos:
                ticket_id = ticket['id']
                empresa_id = ticket['empresa_id']

                # 2. Marcar el ticket como escalado para evitar bucles de ejecución
                cursor.execute("UPDATE tickets SET escalado = 1 WHERE id = %s", (ticket_id,))

                # 3. Registrar el evento automáticamente en la bitácora (ticket_historial)
                cursor.execute("""
                    INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                    VALUES (%s, 1, 'CAMBIO_ESTADO', 'SLA Vencido: Sistema ejecutó escalamiento automático al supervisor.', NOW())
                """, (ticket_id,))

                # 4. Generar notificación interna para los administradores / supervisores de la empresa
                cursor.execute("""
                    SELECT id FROM users WHERE empresa_id = %s AND rol = 'Administrador'
                """, (empresa_id,))
                admins = cursor.fetchall()

                for admin in admins:
                    cursor.execute("""
                        INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
                        VALUES (%s, 'SLA', %s, %s, %s, NOW())
                    """, (
                        admin['id'], 
                        ticket_id, 
                        f"SLA Vencido: {ticket['codigo']}", 
                        f"El ticket '{ticket['asunto']}' superó su tiempo límite de atención y fue escalado automáticamente."
                    ))

        conexion.commit()
    except Exception as e:
        conexion.rollback()
        print(f"[ERROR SLA CRON] Error en tarea de escalamiento automático: {e}")
    finally:
        conexion.close()


def iniciar_scheduler():
    """Inicializa el planificador de tareas en segundo plano (simulador de Cron)."""
    scheduler = BackgroundScheduler()
    # Configurado para evaluar los tickets vencidos cada 5 minutos de forma automática
    scheduler.add_job(func=tarea_escalamiento_automatico, trigger="interval", minutes=5)
    scheduler.start()