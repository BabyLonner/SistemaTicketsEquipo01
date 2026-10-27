"""
Consultas que antes eran VISTAS de MySQL (CREATE VIEW).

Se dejan aquí como subconsultas para que el sistema no dependa de vistas
ni de triggers en el servidor (PythonAnywhere). Se usan así:

    cur.execute(f"SELECT * FROM {V_TICKETS} AS v WHERE v.id = %s", (ticket_id,))

El semáforo del SLA se vuelve a calcular en Python con aplicar_sla()
(Módulo 4: "cálculo de diferencia de timestamps en Python").
"""
from utils import ahora, calcular_sla

# Módulo 1: datos del usuario para la sesión (superusuario = sin empresa)
V_USUARIOS_SESION = """(
    SELECT u.id, u.nombre, u.correo, u.password_hash, u.rol, u.activo,
           u.area_id, a.nombre AS area, u.empresa_id,
           e.codigo AS empresa_codigo, e.nombre AS empresa, e.titulo_sistema,
           e.color_primario, e.color_secundario, e.logo_url,
           COALESCE(e.activo, 1) AS empresa_activa
      FROM users u
      LEFT JOIN empresas e ON e.id = u.empresa_id
      LEFT JOIN areas a    ON a.id = u.area_id
)"""

# Módulos 2, 4 y 6: tickets con código, nombres y campos del SLA
V_TICKETS = """(
  SELECT x.*,
         CASE x.semaforo WHEN 'rojo' THEN 3 WHEN 'amarillo' THEN 2 WHEN 'verde' THEN 1 ELSE 0 END AS urgencia
  FROM (
    SELECT t.id,
           CONCAT(e.prefijo_ticket, '-', LPAD(t.numero, 4, '0')) AS codigo,
           t.numero, t.asunto, t.descripcion, t.estado,
           t.empresa_id, e.nombre AS empresa, e.codigo AS empresa_codigo,
           t.area_id, a.nombre AS area,
           t.categoria_id, c.nombre AS categoria,
           t.prioridad_id, p.nombre AS prioridad, p.nivel AS prioridad_nivel, p.sla_horas,
           t.solicitante_id, s.nombre AS solicitante,
           t.tecnico_id, COALESCE(tec.nombre, 'Sin asignar') AS tecnico,
           t.created_at, t.updated_at, t.fecha_limite, t.fecha_resolucion, t.fecha_cierre,
           TIMESTAMPDIFF(MINUTE, t.created_at, COALESCE(t.fecha_resolucion, t.fecha_cierre, NOW())) AS minutos_transcurridos,
           IF(t.estado IN ('Resuelto', 'Cerrado'), NULL, TIMESTAMPDIFF(MINUTE, NOW(), t.fecha_limite)) AS minutos_restantes,
           ROUND(100 * TIMESTAMPDIFF(MINUTE, t.created_at, COALESCE(t.fecha_resolucion, t.fecha_cierre, NOW()))
                 / (p.sla_horas * 60), 1) AS porcentaje_sla,
           CASE
             WHEN t.estado IN ('Resuelto', 'Cerrado') THEN
               IF(COALESCE(t.fecha_resolucion, t.fecha_cierre) <= t.fecha_limite, 'cumplido', 'incumplido')
             WHEN NOW() > t.fecha_limite THEN 'rojo'
             WHEN TIMESTAMPDIFF(MINUTE, t.created_at, NOW()) >= p.sla_horas * 60 * 0.75 THEN 'amarillo'
             ELSE 'verde'
           END AS semaforo,
           (SELECT ev.ruta FROM ticket_evidencias ev WHERE ev.ticket_id = t.id ORDER BY ev.orden LIMIT 1) AS miniatura,
           (SELECT COUNT(*) FROM ticket_evidencias ev WHERE ev.ticket_id = t.id) AS total_evidencias
      FROM tickets t
      JOIN empresas    e   ON e.id = t.empresa_id
      LEFT JOIN areas  a   ON a.id = t.area_id
      JOIN categorias  c   ON c.id = t.categoria_id
      JOIN prioridades p   ON p.id = t.prioridad_id
      JOIN users       s   ON s.id = t.solicitante_id
      LEFT JOIN users  tec ON tec.id = t.tecnico_id
  ) AS x
)"""

# Módulo 3: línea de tiempo del ticket
V_TICKET_TIMELINE = """(
    SELECT h.id, h.ticket_id, t.empresa_id, h.tipo, h.estado_anterior, h.estado_nuevo,
           ta.nombre AS tecnico_anterior, tn.nombre AS tecnico_nuevo,
           h.comentario, h.usuario_id, u.nombre AS usuario, u.rol AS usuario_rol,
           h.created_at, TIMESTAMPDIFF(MINUTE, h.created_at, NOW()) AS minutos_desde
      FROM ticket_historial h
      JOIN tickets t     ON t.id  = h.ticket_id
      JOIN users u       ON u.id  = h.usuario_id
      LEFT JOIN users ta ON ta.id = h.tecnico_anterior_id
      LEFT JOIN users tn ON tn.id = h.tecnico_nuevo_id
)"""


def aplicar_sla(fila, momento=None):
    """Recalcula en Python el semáforo, los minutos y la urgencia del ticket."""
    if fila and fila.get("created_at") and fila.get("fecha_limite"):
        calcular_sla(fila, momento or ahora())
    return fila


def aplicar_sla_lista(filas):
    momento = ahora()
    for f in filas:
        aplicar_sla(f, momento)
    return filas
