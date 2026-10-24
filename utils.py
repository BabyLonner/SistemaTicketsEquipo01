"""Funciones de apoyo: hora de Perú, cálculo del SLA (Módulo 4) y formatos."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

ESTADOS = ("Abierto", "En proceso", "Resuelto", "Cerrado")
ESTADOS_FINALES = ("Resuelto", "Cerrado")
ROLES = ("Superusuario", "Administrador", "Técnico", "Solicitante")
ROLES_EMPRESA = ("Administrador", "Técnico", "Solicitante")
UMBRAL_AMARILLO = 0.75   # al 75 % del plazo el semáforo pasa a amarillo

TZ_PERU = timezone(timedelta(hours=-5))


def ahora():
    """Hora actual de Perú (sin zona), igual en la PC y en PythonAnywhere (UTC)."""
    return datetime.now(TZ_PERU).replace(tzinfo=None, microsecond=0)


# ---------------------------------------------------------------------
#  Módulo 4: SLA y semáforo  (diferencia de timestamps en Python)
# ---------------------------------------------------------------------
def duracion_texto(minutos):
    """125 -> '2 h 5 min', 3000 -> '2 d 2 h'."""
    minutos = int(abs(minutos))
    dias, resto = divmod(minutos, 1440)
    horas, mins = divmod(resto, 60)
    if dias:
        return f"{dias} d {horas} h" if horas else f"{dias} d"
    if horas:
        return f"{horas} h {mins} min" if mins else f"{horas} h"
    return f"{mins} min"


def calcular_sla(ticket, momento=None):
    """Agrega al ticket los campos calculados del SLA.

    semaforo:  verde (< 75 % del plazo) | amarillo (>= 75 %) | rojo (vencido)
               cumplido / incumplido cuando ya se resolvió o cerró
    urgencia:  3 rojo, 2 amarillo, 1 verde, 0 terminado  (para ordenar el listado)
    """
    momento = momento or ahora()
    creado = ticket["created_at"]
    limite = ticket["fecha_limite"]
    plazo_min = max(int((limite - creado).total_seconds() // 60), 1)

    if ticket["estado"] in ESTADOS_FINALES:
        fin = ticket.get("fecha_resolucion") or ticket.get("fecha_cierre") or momento
        transcurrido = int((fin - creado).total_seconds() // 60)
        semaforo = "cumplido" if fin <= limite else "incumplido"
        restante = None
        texto = "Cumplido" if semaforo == "cumplido" else "Fuera de plazo"
    else:
        transcurrido = int((momento - creado).total_seconds() // 60)
        restante = int((limite - momento).total_seconds() // 60)
        if restante < 0:
            semaforo, texto = "rojo", f"Vencido hace {duracion_texto(restante)}"
        elif transcurrido >= plazo_min * UMBRAL_AMARILLO:
            semaforo, texto = "amarillo", f"Quedan {duracion_texto(restante)}"
        else:
            semaforo, texto = "verde", f"Quedan {duracion_texto(restante)}"

    ticket["minutos_transcurridos"] = transcurrido
    ticket["minutos_restantes"] = restante
    ticket["porcentaje_sla"] = min(round(100 * transcurrido / plazo_min), 100)
    ticket["semaforo"] = semaforo
    ticket["sla_texto"] = texto
    ticket["urgencia"] = {"rojo": 3, "amarillo": 2, "verde": 1}.get(semaforo, 0)
    ticket["transcurrido_texto"] = duracion_texto(transcurrido)
    return ticket


def ordenar_por_urgencia(tickets):
    """Rojo primero (el más vencido arriba), luego amarillo, verde y terminados."""
    return sorted(
        tickets,
        key=lambda t: (
            -t["urgencia"],
            t["minutos_restantes"] if t["minutos_restantes"] is not None else 0,
            -t["created_at"].timestamp(),
        ),
    )


# ---------------------------------------------------------------------
#  Formatos
# ---------------------------------------------------------------------
def hace(fecha, momento=None):
    """Fecha relativa: 'hace 3 h 10 min', 'ayer', 'hace 4 d'."""
    if not fecha:
        return ""
    momento = momento or ahora()
    minutos = int((momento - fecha).total_seconds() // 60)
    if minutos < 1:
        return "hace un momento"
    if minutos < 60:
        return f"hace {minutos} min"
    if minutos < 1440:
        h, m = divmod(minutos, 60)
        return f"hace {h} h {m} min" if m else f"hace {h} h"
    dias = minutos // 1440
    return "ayer" if dias == 1 else f"hace {dias} d"


def iniciales(nombre):
    partes = [p for p in (nombre or "").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    # "Ana Díaz" -> AD, "Christian Llontop Flores" -> CL, "Julio Cesar Salazar Tineo" -> JS
    segunda = partes[2] if len(partes) >= 4 else partes[1]
    return (partes[0][0] + segunda[0]).upper()


def nombre_corto(nombre):
    """'Julio Cesar Salazar Tineo' -> 'Julio Salazar', 'Ana Díaz' -> 'Ana Díaz'."""
    partes = (nombre or "").split()
    if len(partes) >= 4:
        return f"{partes[0]} {partes[2]}"
    if len(partes) == 3:
        return f"{partes[0]} {partes[1]}"
    return " ".join(partes)


def codigo_ticket(prefijo, numero):
    return f"{prefijo}-{int(numero):04d}"


def dominio_de(correo):
    return (correo or "").strip().lower().rsplit("@", 1)[-1] if "@" in (correo or "") else ""


CORREO_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
DOMINIO_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def correo_valido(correo):
    return bool(CORREO_RE.match((correo or "").strip().lower()))


def slug(texto):
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return texto[:30] or "empresa"


def entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def fecha_iso(valor):
    return valor.isoformat(timespec="seconds") if valor else None
