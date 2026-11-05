"""
MÓDULO 8 — Ruta que llama cron-job.org una vez al día. No pide sesión: se protege con CRON_TOKEN.

    POST /tareas/enviar-reportes      encabezado X-Cron-Token: <clave>
"""
import hmac

from flask import Blueprint, jsonify, request

import config
from envios import procesar_envios_programados
from utils import ahora

tareas_bp = Blueprint("tareas", __name__)


@tareas_bp.post("/tareas/enviar-reportes")
def enviar_reportes_programados():
    clave = request.headers.get("X-Cron-Token", "")
    # compare_digest: compara en tiempo constante, no revela cuántos caracteres coinciden
    if not config.CRON_TOKEN or not hmac.compare_digest(clave.encode(), config.CRON_TOKEN.encode()):
        return jsonify(ok=False, error="No autorizado."), 401
    resultados, errores = procesar_envios_programados(ahora().date())
    # 500 si algo falló: así cron-job.org puede avisar por correo
    return jsonify(ok=errores == 0, resultados=resultados), (500 if errores else 200)