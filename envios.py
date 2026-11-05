"""
MÓDULO 8 — Genera el reporte de un periodo y lo envía a los correos indicados.

Lo usan el botón "Enviar ahora" (cuenta.py) y la tarea programada (enviar_reportes.py).
Cada intento queda en la tabla reporte_envios, con el error si lo hubo.

Programación por empresa (tabla reporte_programacion): activado o no y día de la semana.
El periodo automático son los 7 días anteriores al día de envío.
"""
from datetime import timedelta

from correo import ErrorCorreo, enviar_correo
from db import conexion, consultar
from reportes import generar_pdf_reporte
from utils import ahora
from verificacion import url_verificacion

CLAVES_FILTROS = ("desde", "hasta", "area", "categoria", "prioridad", "estado", "tecnico", "q")
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")   # como date.weekday()


def semana_anterior(hoy=None):
    """Lunes y domingo de la semana pasada (fechas iniciales del envío manual)."""
    hoy = hoy or ahora().date()
    hasta = hoy - timedelta(days=hoy.weekday() + 1)
    return hasta - timedelta(days=6), hasta


def programacion_de(empresa_id):
    """Sin fila en la tabla: activado y los lunes."""
    fila = consultar("SELECT activo, dia_semana FROM reporte_programacion WHERE empresa_id = %s", (empresa_id,), uno=True)
    return fila or {"activo": 1, "dia_semana": 0}


def ultimo_dia_programado(dia_semana, hoy):
    """Fecha más reciente (hoy incluido) que cae en ese día de la semana."""
    return hoy - timedelta(days=(hoy.weekday() - dia_semana) % 7)


def periodo_de_envio(fecha_envio):
    """Los 7 días anteriores al día de envío."""
    return fecha_envio - timedelta(days=7), fecha_envio - timedelta(days=1)


def proximo_envio(empresa_id, dia_semana, hoy):
    fecha = hoy + timedelta(days=(dia_semana - hoy.weekday()) % 7)
    if fecha == hoy and ya_enviado(empresa_id, periodo_de_envio(fecha)[0]):
        fecha += timedelta(days=7)
    return fecha


def ya_enviado(empresa_id, desde):
    """El envío automático de ese periodo ya salió bien."""
    return bool(consultar(
        """SELECT 1 FROM reporte_envios
            WHERE empresa_id = %s AND origen = 'automatico' AND periodo_desde = %s AND estado = 'ok' LIMIT 1""",
        (empresa_id, desde), uno=True))


def fallo_el_envio(empresa_id, desde):
    """El envío automático de ese periodo se intentó y falló: se reintenta al día siguiente."""
    return bool(consultar(
        """SELECT 1 FROM reporte_envios
            WHERE empresa_id = %s AND origen = 'automatico' AND periodo_desde = %s AND estado = 'error' LIMIT 1""",
        (empresa_id, desde), uno=True))


def destinatarios_de(empresa_id):
    filas = consultar("SELECT correo FROM reporte_destinatarios WHERE empresa_id = %s ORDER BY correo", (empresa_id,))
    return [d["correo"] for d in filas]


def destinatarios_semanales(empresa_id):
    filas = consultar("SELECT correo FROM reporte_destinatarios WHERE empresa_id = %s AND semanal = 1 ORDER BY correo",
                      (empresa_id,))
    return [d["correo"] for d in filas]


def enviar_reporte_empresa(empresa, desde, hasta, origen, correos, autor="Envío automático", usuario_id=None):
    """Devuelve (salió bien, mensaje). empresa = fila de la tabla empresas."""
    if not correos:
        return False, "No hay destinatarios para este envío."
    filtros = {clave: "" for clave in CLAVES_FILTROS}
    filtros.update(desde=f"{desde:%Y-%m-%d}", hasta=f"{hasta:%Y-%m-%d}")
    pdf, codigo = generar_pdf_reporte(empresa, filtros, autor, usuario_id)
    texto = (f"Reporte de tickets de {empresa['nombre']} del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}.\n"
             "El PDF adjunto incluye los tickets creados en ese periodo.\n\n"
             f"Para comprobar que el documento es auténtico: {url_verificacion(codigo)}\n\n"
             "Mesa de Ayuda TI - mensaje automático")
    try:
        rechazados = enviar_correo(correos, f"Reporte de tickets {desde:%d/%m} al {hasta:%d/%m} - {empresa['nombre']}",
                                   texto, pdf, f"reporte_{empresa['codigo']}_{desde:%Y%m%d}.pdf")
        estado = "ok"
        detalle = f"No aceptados: {', '.join(rechazados)}" if rechazados else None
        mensaje = detalle or f"Reporte enviado a {len(correos)} destinatario(s)."
    except ErrorCorreo as e:
        estado, detalle, mensaje = "error", str(e)[:500], str(e)
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO reporte_envios
                 (empresa_id, origen, periodo_desde, periodo_hasta, destinatarios, codigo_reporte, estado, detalle)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (empresa["id"], origen, desde, hasta, ", ".join(correos)[:1000], codigo, estado, detalle))
    con.commit()
    return estado == "ok", mensaje

def procesar_envios_programados(hoy, forzar=False):
    """Revisa la programación de cada empresa. Devuelve el resultado de cada una y cuántos envíos fallaron."""
    resultados, errores = [], 0
    for empresa in consultar("SELECT * FROM empresas WHERE activo = 1 ORDER BY id"):
        nombre = empresa["nombre"]
        programacion = programacion_de(empresa["id"])
        if not programacion["activo"]:
            resultados.append(f"{nombre}: envío automático desactivado.")
            continue
        correos = destinatarios_semanales(empresa["id"])
        if not correos:
            resultados.append(f"{nombre}: sin destinatarios con envío semanal.")
            continue
        fecha_envio = ultimo_dia_programado(programacion["dia_semana"], hoy)
        desde, hasta = periodo_de_envio(fecha_envio)
        if not forzar:
            if ya_enviado(empresa["id"], desde):
                resultados.append(f"{nombre}: ya se envió el reporte del {desde:%d/%m} al {hasta:%d/%m}.")
                continue
            if fecha_envio != hoy and not fallo_el_envio(empresa["id"], desde):
                resultados.append(f"{nombre}: hoy no le toca y no hay envíos pendientes.")
                continue
        try:
            ok, mensaje = enviar_reporte_empresa(empresa, desde, hasta, "automatico", correos)
        except Exception as e:  # noqa: BLE001  una empresa con problemas no detiene a las demás
            ok, mensaje = False, f"Error inesperado: {e}"
        resultados.append(f"{nombre} ({desde:%d/%m} al {hasta:%d/%m}): {'OK' if ok else 'NO ENVIADO'} - {mensaje}")
        errores += 0 if ok else 1
    return resultados, errores

