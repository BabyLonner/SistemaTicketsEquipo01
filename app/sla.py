"""Cálculo del SLA y del semáforo (módulo 4)."""
from datetime import datetime, timezone

# Tiempo máximo de resolución por prioridad, en horas
HORAS_SLA = {"Alta": 4, "Media": 24, "Baja": 72}
# Desde qué porcentaje del plazo el semáforo pasa a amarillo
UMBRAL_AMARILLO = 0.75


def ahora():
    """Hora actual en UTC sin zona (así se guarda en la base de datos)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def duracion(segundos):
    minutos = max(1, round(segundos / 60))
    if minutos < 60:
        return f"{minutos} min"
    horas, resto_min = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h {resto_min} min" if horas < 10 and resto_min else f"{horas} h"
    dias, resto_h = divmod(horas, 24)
    return f"{dias} d {resto_h} h" if resto_h else f"{dias} d"


def calcular(prioridad, creado, cierre=None, momento=None):
    """Devuelve el nivel del semáforo (verde, amarillo, rojo) y un texto para mostrar."""
    limite = HORAS_SLA[prioridad] * 3600
    base = {"limite": limite, "horas_limite": HORAS_SLA[prioridad]}

    if cierre:
        total = (cierre - creado).total_seconds()
        a_tiempo = total <= limite
        return {**base, "nivel": "verde" if a_tiempo else "rojo",
                "texto": "Cumplido" if a_tiempo else "Fuera de plazo",
                "cerrado": True, "transcurrido": total, "ratio": total / limite}

    transcurrido = ((momento or ahora()) - creado).total_seconds()
    ratio = transcurrido / limite
    if ratio >= 1:
        return {**base, "nivel": "rojo", "texto": "Vencido hace " + duracion(transcurrido - limite),
                "cerrado": False, "transcurrido": transcurrido, "ratio": ratio}
    return {**base, "nivel": "amarillo" if ratio >= UMBRAL_AMARILLO else "verde",
            "texto": "Quedan " + duracion(limite - transcurrido),
            "cerrado": False, "transcurrido": transcurrido, "ratio": ratio}
