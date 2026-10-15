"""Lógica de negocio compartida por las páginas web y la API REST."""
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import case, func, select

from .archivos import eliminar_archivos, guardar_fotos, validar_fotos
from .constantes import AREAS, CATEGORIAS, EMPRESAS, ESTADOS, ESTADOS_CIERRE, PRIORIDADES, ROLES
from .errores import ErrorNegocio
from .extensions import db
from .models import Notificacion, Ticket, TicketHistorial, Usuario
from .sla import ahora

PATRON_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ---------------------------------------------------------------- permisos
def puede_ver(usuario, ticket):
    return usuario.rol != "Solicitante" or ticket.solicitante_id == usuario.id


def obtener_ticket(usuario, ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not puede_ver(usuario, ticket):
        raise ErrorNegocio("No encontramos ese ticket.", 404)
    return ticket


def consulta_visible(usuario, empresa=None):
    consulta = Ticket.query
    if usuario.rol == "Solicitante":
        consulta = consulta.filter(Ticket.solicitante_id == usuario.id)
    if empresa:
        consulta = consulta.filter(Ticket.empresa == empresa)
    return consulta


# ---------------------------------------------------------------- notificaciones
def notificar(usuario_id, tipo, ticket, mensaje, excepto=None):
    if usuario_id and usuario_id != excepto:
        db.session.add(Notificacion(usuario_id=usuario_id, tipo=tipo, referencia_ticket=ticket.id, mensaje=mensaje))


def contar_no_leidas(usuario):
    return Notificacion.query.filter_by(usuario_id=usuario.id, leido=False).count()


def marcar_leidas(usuario, ids=None):
    consulta = Notificacion.query.filter_by(usuario_id=usuario.id, leido=False)
    if ids is not None:
        consulta = consulta.filter(Notificacion.id.in_(ids))
    total = consulta.update({"leido": True}, synchronize_session=False)
    db.session.commit()
    return total


# ---------------------------------------------------------------- tickets
def _validar_campos_ticket(datos, parcial=False):
    errores = {}
    limpio = {}
    if not parcial or "asunto" in datos:
        asunto = (datos.get("asunto") or "").strip()
        if not 5 <= len(asunto) <= 120:
            errores["asunto"] = "Escribe un asunto de 5 a 120 caracteres."
        limpio["asunto"] = asunto
    if not parcial or "descripcion" in datos:
        descripcion = (datos.get("descripcion") or "").strip()
        if len(descripcion) < 10:
            errores["descripcion"] = "Describe el problema con al menos 10 caracteres."
        limpio["descripcion"] = descripcion
    if not parcial or "categoria" in datos:
        categoria = datos.get("categoria") or ""
        if categoria not in CATEGORIAS:
            errores["categoria"] = "Elige una categoría."
        limpio["categoria"] = categoria
    if not parcial or "prioridad" in datos:
        prioridad = datos.get("prioridad") or ""
        if prioridad not in PRIORIDADES:
            errores["prioridad"] = "Elige una prioridad."
        limpio["prioridad"] = prioridad
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)
    return limpio


def crear_ticket(solicitante, datos, archivos=()):
    campos = _validar_campos_ticket(datos)
    fotos_validas = validar_fotos(archivos)

    ticket = Ticket(**campos, estado="Abierto", empresa=solicitante.empresa, solicitante_id=solicitante.id)
    db.session.add(ticket)
    db.session.flush()

    ticket.fotos = guardar_fotos(fotos_validas)
    n = len(ticket.fotos)
    texto = "Ticket registrado."
    if n:
        texto = "Se adjuntó 1 foto de evidencia." if n == 1 else f"Se adjuntaron {n} fotos de evidencia."
    db.session.add(TicketHistorial(ticket_id=ticket.id, usuario_id=solicitante.id, tipo="creado", texto=texto))

    for admin in Usuario.query.filter_by(rol="Administrador", activo=True):
        notificar(admin.id, "nuevo", ticket, f"Nuevo ticket {ticket.codigo} por asignar", excepto=solicitante.id)

    db.session.commit()
    return ticket


def actualizar_ticket(ticket, datos, actor):
    es_dueno = ticket.solicitante_id == actor.id and ticket.estado == "Abierto"
    if actor.rol != "Administrador" and not es_dueno:
        raise ErrorNegocio("Solo el administrador o el solicitante (con el ticket abierto) pueden editarlo.", 403)
    campos = _validar_campos_ticket(datos, parcial=True)
    for clave, valor in campos.items():
        setattr(ticket, clave, valor)
    db.session.commit()
    return ticket


def eliminar_ticket(ticket):
    eliminar_archivos(list(ticket.fotos))
    db.session.delete(ticket)
    db.session.commit()


def asignar(ticket, tecnico_id, actor):
    try:
        tecnico = db.session.get(Usuario, int(tecnico_id))
    except (TypeError, ValueError):
        tecnico = None
    if tecnico is None or tecnico.rol != "Técnico" or not tecnico.activo:
        raise ErrorNegocio("Elige un técnico activo.", 422, {"tecnico_id": "Elige un técnico activo."})
    if ticket.estado == "Cerrado":
        raise ErrorNegocio("No se puede asignar un ticket cerrado.", 409)
    if ticket.tecnico_id == tecnico.id:
        raise ErrorNegocio("El ticket ya está asignado a esa persona.", 409)

    ticket.tecnico_id = tecnico.id
    db.session.add(TicketHistorial(ticket_id=ticket.id, usuario_id=actor.id, tipo="asignado",
                                   texto=f"Ticket asignado a {tecnico.nombre}"))
    notificar(tecnico.id, "asignacion", ticket, f"Se te asignó el ticket {ticket.codigo}", excepto=actor.id)
    notificar(ticket.solicitante_id, "asignacion", ticket, f"{ticket.codigo} fue asignado a {tecnico.nombre}", excepto=actor.id)
    db.session.commit()
    return ticket


def cambiar_estado(ticket, nuevo, comentario, actor):
    if actor.rol == "Solicitante":
        raise ErrorNegocio("Solo el administrador o el técnico pueden cambiar el estado.", 403)
    if actor.rol == "Técnico" and ticket.tecnico_id != actor.id:
        raise ErrorNegocio("Solo el técnico asignado puede cambiar el estado de este ticket.", 403)

    comentario = (comentario or "").strip()
    errores = {}
    if nuevo not in ESTADOS:
        errores["estado"] = "Elige un estado válido."
    elif nuevo == ticket.estado:
        errores["estado"] = f"Elige un estado distinto al actual ({ticket.estado})."
    if len(comentario) < 5:
        errores["comentario"] = "Escribe un comentario para poder guardar el cambio."
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)

    anterior = ticket.estado
    ticket.estado = nuevo
    if nuevo in ESTADOS_CIERRE:
        ticket.cerrado_at = ticket.cerrado_at or ahora()
    else:
        ticket.cerrado_at = None

    db.session.add(TicketHistorial(ticket_id=ticket.id, usuario_id=actor.id, tipo="estado",
                                   estado_anterior=anterior, estado_nuevo=nuevo, texto=comentario))
    mensaje = f"{ticket.codigo} cambió a {nuevo}"
    notificar(ticket.solicitante_id, "estado", ticket, mensaje, excepto=actor.id)
    notificar(ticket.tecnico_id, "estado", ticket, mensaje, excepto=actor.id)
    db.session.commit()
    return ticket


def comentar(ticket, texto, actor):
    texto = (texto or "").strip()
    if len(texto) < 2:
        raise ErrorNegocio("Escribe el comentario antes de publicarlo.", 422, {"texto": "Escribe el comentario."})
    db.session.add(TicketHistorial(ticket_id=ticket.id, usuario_id=actor.id, tipo="comentario", texto=texto))
    mensaje = f"Nuevo comentario en {ticket.codigo}"
    notificar(ticket.solicitante_id, "comentario", ticket, mensaje, excepto=actor.id)
    notificar(ticket.tecnico_id, "comentario", ticket, mensaje, excepto=actor.id)
    db.session.commit()


def _orden_urgencia(ticket):
    s = ticket.sla
    # Abiertos primero (más plazo consumido arriba); cerrados al final (más recientes arriba)
    if s["cerrado"]:
        return (1, -ticket.cerrado_at.timestamp())
    return (0, -s["ratio"])


def listar_tickets(usuario, empresa=None, filtros=None):
    """Tickets visibles, filtrados y ordenados por urgencia. Devuelve (lista, resumen de alertas)."""
    filtros = filtros or {}
    visibles = consulta_visible(usuario, empresa).all()

    vencidos = sum(1 for t in visibles if not t.sla["cerrado"] and t.sla["nivel"] == "rojo")
    por_vencer = sum(1 for t in visibles if not t.sla["cerrado"] and t.sla["nivel"] == "amarillo")

    q = (filtros.get("q") or "").strip().lower()
    tecnico = filtros.get("tecnico") or ""
    lista = []
    for t in visibles:
        if q and q not in f"{t.codigo} {t.asunto}".lower():
            continue
        if filtros.get("estado") and t.estado != filtros["estado"]:
            continue
        if filtros.get("prioridad") and t.prioridad != filtros["prioridad"]:
            continue
        if tecnico == "sin" and t.tecnico_id:
            continue
        if tecnico not in ("", "sin") and str(t.tecnico_id) != str(tecnico):
            continue
        if filtros.get("urgentes") and (t.sla["cerrado"] or t.sla["nivel"] == "verde"):
            continue
        lista.append(t)

    lista.sort(key=_orden_urgencia)
    return lista, {"total": len(visibles), "vencidos": vencidos, "por_vencer": por_vencer}


# ---------------------------------------------------------------- reportes
def zona_local():
    return ZoneInfo(current_app.config["ZONA_HORARIA"])


def hoy_local():
    return datetime.now(zona_local()).date()


def rango_utc(desde, hasta):
    """Convierte fechas locales (AAAA-MM-DD) a datetimes UTC para filtrar."""
    zona = zona_local()

    def convertir(texto, hora):
        try:
            fecha = datetime.strptime(texto, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
        return datetime.combine(fecha, hora, zona).astimezone(timezone.utc).replace(tzinfo=None)

    return convertir(desde, time.min), convertir(hasta, time.max)


def filtros_reporte(args):
    hoy = hoy_local()
    return {
        "desde": args.get("desde") or (hoy - timedelta(days=30)).isoformat(),
        "hasta": args.get("hasta") or hoy.isoformat(),
        "area": args.get("area") if args.get("area") in AREAS else "",
        "tecnico": args.get("tecnico") or "",
    }


def consulta_reporte(usuario, empresa, filtros):
    consulta = consulta_visible(usuario, empresa)
    inicio, fin = rango_utc(filtros["desde"], filtros["hasta"])
    if inicio:
        consulta = consulta.filter(Ticket.created_at >= inicio)
    if fin:
        consulta = consulta.filter(Ticket.created_at <= fin)
    if filtros["area"]:
        consulta = consulta.filter(Ticket.solicitante_id.in_(
            select(Usuario.id).where(Usuario.area == filtros["area"])))
    if filtros["tecnico"] == "sin":
        consulta = consulta.filter(Ticket.tecnico_id.is_(None))
    elif filtros["tecnico"]:
        consulta = consulta.filter(Ticket.tecnico_id == filtros["tecnico"])
    return consulta


def resumen(usuario, empresa, filtros):
    """Datos del dashboard. Los conteos se hacen con GROUP BY en la base de datos."""
    base = consulta_reporte(usuario, empresa, filtros)
    ids = base.with_entities(Ticket.id).subquery()
    en_rango = Ticket.id.in_(select(ids.c.id))

    def agrupar(columna):
        filas = db.session.query(columna, func.count(Ticket.id)).filter(en_rango).group_by(columna).all()
        return {clave: total for clave, total in filas}

    por_estado = agrupar(Ticket.estado)
    por_prioridad = agrupar(Ticket.prioridad)
    por_categoria = agrupar(Ticket.categoria)

    filas_resp = (db.session.query(
        Ticket.tecnico_id,
        func.count(Ticket.id),
        func.sum(case((Ticket.estado == "En proceso", 1), else_=0)),
        func.sum(case((Ticket.estado.in_(ESTADOS_CIERRE), 1), else_=0)),
    ).filter(en_rango).group_by(Ticket.tecnico_id).all())
    conteo_resp = {fila[0]: fila[1:] for fila in filas_resp}

    # El semáforo depende de la hora actual, por eso se calcula en Python
    tickets = base.all()
    sla = {"verde": 0, "amarillo": 0, "rojo": 0}
    verdes_por_tecnico = {}
    for t in tickets:
        nivel = t.sla["nivel"]
        sla[nivel] += 1
        if nivel == "verde":
            verdes_por_tecnico[t.tecnico_id] = verdes_por_tecnico.get(t.tecnico_id, 0) + 1

    responsables = []
    for tecnico in Usuario.query.filter_by(rol="Técnico").order_by(Usuario.nombre):
        asignados, en_proceso, resueltos = conteo_resp.get(tecnico.id, (0, 0, 0))
        a_tiempo = round(verdes_por_tecnico.get(tecnico.id, 0) / asignados * 100) if asignados else None
        responsables.append({"id": tecnico.id, "nombre": tecnico.nombre, "asignados": asignados,
                             "en_proceso": int(en_proceso or 0), "resueltos": int(resueltos or 0), "a_tiempo": a_tiempo})

    total = len(tickets)
    return {
        "total": total,
        "por_estado": {e: por_estado.get(e, 0) for e in ESTADOS},
        "por_prioridad": {p: por_prioridad.get(p, 0) for p in PRIORIDADES},
        "por_categoria": {c: por_categoria.get(c, 0) for c in CATEGORIAS},
        "sla": sla,
        "sla_porcentaje": round(sla["verde"] / total * 100) if total else None,
        "responsables": responsables,
        "sin_asignar": conteo_resp.get(None, (0,))[0],
    }


# ---------------------------------------------------------------- usuarios
def _validar_usuario(datos, usuario=None):
    errores = {}
    nombre = (datos.get("nombre") or "").strip()
    correo = (datos.get("correo") or "").strip().lower()
    clave = datos.get("password") or datos.get("clave") or ""
    rol = datos.get("rol") or ""
    empresa = datos.get("empresa") or ""
    area = datos.get("area") or ""

    if len(nombre) < 3:
        errores["nombre"] = "Escribe el nombre completo."
    if not PATRON_CORREO.match(correo):
        errores["correo"] = "Escribe un correo válido."
    else:
        repetido = Usuario.query.filter(func.lower(Usuario.correo) == correo)
        if usuario:
            repetido = repetido.filter(Usuario.id != usuario.id)
        if repetido.first():
            errores["correo"] = "Ya existe un usuario con ese correo."
    if (usuario is None or clave) and len(clave) < 8:
        errores["password"] = "La contraseña debe tener al menos 8 caracteres."
    if rol not in ROLES:
        errores["rol"] = "Elige un rol."
    if empresa not in EMPRESAS:
        errores["empresa"] = "Elige una empresa."
    if area and area not in AREAS:
        errores["area"] = "Elige un área válida."
    if errores:
        raise ErrorNegocio("Revisa los campos marcados.", 422, errores)
    return {"nombre": nombre, "correo": correo, "clave": clave, "rol": rol, "empresa": empresa, "area": area or None}


def _activo(valor, defecto=True):
    if valor is None:
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).lower() in ("1", "true", "on", "si", "sí")


def crear_usuario(datos):
    limpio = _validar_usuario(datos)
    usuario = Usuario(nombre=limpio["nombre"], correo=limpio["correo"], rol=limpio["rol"],
                      empresa=limpio["empresa"], area=limpio["area"], activo=_activo(datos.get("activo")))
    usuario.set_password(limpio["clave"])
    db.session.add(usuario)
    db.session.commit()
    return usuario


def actualizar_usuario(usuario, datos, actor):
    limpio = _validar_usuario(datos, usuario)
    activo = _activo(datos.get("activo"), usuario.activo)
    if usuario.id == actor.id and (limpio["rol"] != "Administrador" or not activo):
        raise ErrorNegocio("No puedes quitarte el rol de administrador ni desactivar tu propia cuenta.", 409)
    usuario.nombre = limpio["nombre"]
    usuario.correo = limpio["correo"]
    usuario.rol = limpio["rol"]
    usuario.empresa = limpio["empresa"]
    usuario.area = limpio["area"]
    usuario.activo = activo
    if limpio["clave"]:
        usuario.set_password(limpio["clave"])
    db.session.commit()
    return usuario


def cambiar_activo(usuario, activo, actor):
    if usuario.id == actor.id:
        raise ErrorNegocio("No puedes desactivar tu propia cuenta.", 409)
    usuario.activo = activo
    db.session.commit()
    return usuario
