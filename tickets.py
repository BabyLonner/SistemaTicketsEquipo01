"""
MÓDULOS 2, 3 y 4 — Tickets con evidencias, asignación/estados/historial y SLA.

Sin triggers: Python calcula la empresa, el área, el correlativo (EPS-0001),
la fecha límite del SLA, el historial y las notificaciones, todo dentro de
una sola transacción (si algo falla, se hace rollback).

Quién ve qué (función alcance):
  Superusuario  -> todas las empresas (o la elegida en la cabecera)
  Administrador -> todos los tickets de su empresa
  Técnico       -> los tickets asignados a él
  Solicitante   -> sus propios tickets
"""
import io
import math
import os
import shutil
import uuid
import warnings
from datetime import timedelta

import pymysql
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from PIL import Image, ImageOps, UnidentifiedImageError

import config
from auth import empresa_filtro, es_super, login_requerido, roles_requeridos
from db import conexion, consultar
from notificaciones import administradores_de, notificar
from utils import (
    ESTADOS,
    ahora,
    calcular_sla,
    codigo_ticket,
    entero,
    fecha_iso,
    hace,
    ordenar_por_urgencia,
)

tickets_bp = Blueprint("tickets", __name__)

POR_PAGINA = 10
MAX_EVIDENCIAS = 3


class ErrorRegla(Exception):
    """Regla de negocio no cumplida (antes eran los SIGNAL de los triggers)."""


# =====================================================================
#  Consultas
# =====================================================================
SQL_TICKETS = """
    SELECT t.id, t.numero, t.empresa_id, t.area_id, t.solicitante_id, t.tecnico_id,
           t.categoria_id, t.prioridad_id, t.asunto, t.descripcion, t.estado,
           t.fecha_limite, t.fecha_resolucion, t.fecha_cierre, t.created_at, t.updated_at,
           e.nombre AS empresa, e.codigo AS empresa_codigo, e.prefijo_ticket,
           a.nombre AS area, c.nombre AS categoria,
           p.nombre AS prioridad, p.nivel AS prioridad_nivel, p.sla_horas,
           s.nombre AS solicitante, s.correo AS solicitante_correo,
           tec.nombre AS tecnico,
           (SELECT ev.id FROM ticket_evidencias ev WHERE ev.ticket_id = t.id
             ORDER BY ev.orden LIMIT 1) AS primera_evidencia_id,
           (SELECT COUNT(*) FROM ticket_evidencias ev WHERE ev.ticket_id = t.id) AS total_evidencias
      FROM tickets t
      JOIN empresas e    ON e.id = t.empresa_id
      LEFT JOIN areas a  ON a.id = t.area_id
      JOIN categorias c  ON c.id = t.categoria_id
      JOIN prioridades p ON p.id = t.prioridad_id
      JOIN users s       ON s.id = t.solicitante_id
      LEFT JOIN users tec ON tec.id = t.tecnico_id
"""


def alcance(usuario, empresa_id=None):
    """Condición WHERE según el rol (el empresa_id SIEMPRE sale del token, nunca del navegador)."""
    rol = usuario["rol"]
    if rol == "Superusuario":
        return ("t.empresa_id = %s", [empresa_id]) if empresa_id else ("1 = 1", [])
    condicion, params = "t.empresa_id = %s", [usuario["empresa_id"]]
    if rol == "Técnico":
        condicion += " AND t.tecnico_id = %s"
        params.append(usuario["id"])
    elif rol == "Solicitante":
        condicion += " AND t.solicitante_id = %s"
        params.append(usuario["id"])
    return condicion, params


def preparar(ticket, momento=None):
    """Código visible + campos del SLA calculados en Python."""
    ticket["codigo"] = codigo_ticket(ticket["prefijo_ticket"], ticket["numero"])
    return calcular_sla(ticket, momento)


def buscar_tickets(usuario, filtros=None, empresa_id=None):
    filtros = filtros or {}
    condicion, params = alcance(usuario, empresa_id)
    condiciones = [condicion]
    if filtros.get("estado") in ESTADOS:
        condiciones.append("t.estado = %s")
        params.append(filtros["estado"])
    if filtros.get("prioridad"):
        condiciones.append("p.nombre = %s")
        params.append(filtros["prioridad"])
    if filtros.get("tecnico") == "sin":
        condiciones.append("t.tecnico_id IS NULL")
    elif entero(filtros.get("tecnico")):
        condiciones.append("t.tecnico_id = %s")
        params.append(entero(filtros["tecnico"]))
    if filtros.get("q"):
        condiciones.append(
            "(t.asunto LIKE %s OR CONCAT(e.prefijo_ticket, '-', LPAD(t.numero, 4, '0')) LIKE %s)"
        )
        params += [f"%{filtros['q']}%"] * 2
    filas = consultar(SQL_TICKETS + " WHERE " + " AND ".join(condiciones), params)
    momento = ahora()
    tickets = [preparar(t, momento) for t in filas]
    if filtros.get("urgentes"):
        tickets = [t for t in tickets if t["semaforo"] in ("rojo", "amarillo")]
    return ordenar_por_urgencia(tickets)


def obtener_ticket(ticket_id, usuario):
    """El ticket solo se encuentra si está dentro del alcance del usuario."""
    condicion, params = alcance(usuario)
    fila = consultar(SQL_TICKETS + f" WHERE t.id = %s AND {condicion}", [ticket_id] + params, uno=True)
    return preparar(fila) if fila else None


def ticket_o_404(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if ticket is None:
        abort(404)
    return ticket


def catalogos():
    return {
        "categorias": consultar("SELECT id, nombre FROM categorias WHERE activo = 1 ORDER BY nombre"),
        "prioridades": consultar("SELECT id, nombre, sla_horas FROM prioridades ORDER BY nivel DESC"),
    }


def tecnicos_de(empresa_id):
    return consultar(
        "SELECT id, nombre FROM users WHERE empresa_id = %s AND rol = 'Técnico' AND activo = 1 ORDER BY nombre",
        (empresa_id,),
    )


def evidencias_de(ticket_id):
    return consultar(
        """SELECT ev.id, ev.orden, ev.nombre_original, ev.mime_type, ev.tamano_bytes,
                  ev.subido_por, u.nombre AS subido_por_nombre, ev.created_at
             FROM ticket_evidencias ev JOIN users u ON u.id = ev.subido_por
            WHERE ev.ticket_id = %s ORDER BY ev.orden""",
        (ticket_id,),
    )


def historial_de(ticket_id):
    filas = consultar(
        """SELECT h.id, h.tipo, h.estado_anterior, h.estado_nuevo, h.comentario, h.created_at,
                  u.nombre AS usuario, u.rol AS usuario_rol,
                  ta.nombre AS tecnico_anterior, tn.nombre AS tecnico_nuevo
             FROM ticket_historial h
             JOIN users u       ON u.id  = h.usuario_id
             LEFT JOIN users ta ON ta.id = h.tecnico_anterior_id
             LEFT JOIN users tn ON tn.id = h.tecnico_nuevo_id
            WHERE h.ticket_id = %s
            ORDER BY h.created_at DESC, h.id DESC""",
        (ticket_id,),
    )
    momento = ahora()
    for h in filas:
        h["hace"] = hace(h["created_at"], momento)
        if h["tipo"] == "CREACION":
            h["titulo"] = "Ticket creado"
        elif h["tipo"] == "ASIGNACION":
            h["titulo"] = (f"Reasignado de {h['tecnico_anterior']} a {h['tecnico_nuevo']}"
                           if h["tecnico_anterior"] else f"Ticket asignado a {h['tecnico_nuevo']}")
        elif h["tipo"] == "CAMBIO_ESTADO":
            h["titulo"] = f"Estado cambiado: {h['estado_anterior']} → {h['estado_nuevo']}"
        else:
            h["titulo"] = "Comentario"
    return filas


# =====================================================================
#  Permisos
# =====================================================================
TRANSICIONES = {
    "Abierto": ["En proceso", "Cerrado"],
    "En proceso": ["Resuelto", "Abierto"],
    "Resuelto": ["Cerrado", "En proceso"],
    "Cerrado": ["En proceso"],
}


def es_gestor(usuario, ticket):
    """Administrador de la empresa del ticket o superusuario."""
    return usuario["rol"] == "Superusuario" or (
        usuario["rol"] == "Administrador" and usuario["empresa_id"] == ticket["empresa_id"]
    )


def estados_permitidos(usuario, ticket):
    actual = ticket["estado"]
    if es_gestor(usuario, ticket):
        opciones = list(TRANSICIONES[actual])
    elif usuario["rol"] == "Técnico" and ticket["tecnico_id"] == usuario["id"]:
        opciones = {"Abierto": ["En proceso"], "En proceso": ["Resuelto", "Abierto"],
                    "Resuelto": ["En proceso"]}.get(actual, [])
    elif ticket["solicitante_id"] == usuario["id"] and actual == "Resuelto":
        opciones = ["Cerrado", "En proceso"]   # confirmar solución o reabrir
    else:
        opciones = []
    if not ticket["tecnico_id"]:
        opciones = [e for e in opciones if e != "En proceso"]
    return opciones


def permisos(usuario, ticket):
    abierto = ticket["estado"] != "Cerrado"
    return {
        "asignar": es_gestor(usuario, ticket) and abierto,
        "estados": estados_permitidos(usuario, ticket),
        "comentar": abierto,
        "adjuntar": abierto and ticket["total_evidencias"] < MAX_EVIDENCIAS and (
            es_gestor(usuario, ticket) or usuario["id"] in (ticket["solicitante_id"], ticket["tecnico_id"])
        ),
        "eliminar": es_gestor(usuario, ticket) or (
            ticket["solicitante_id"] == usuario["id"] and ticket["estado"] == "Abierto" and not ticket["tecnico_id"]
        ),
    }


# =====================================================================
#  Fotos de evidencia (validación en 4 capas + miniatura)
# =====================================================================
EXTENSIONES = {"jpg", "jpeg", "png", "webp"}
MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANO_MAXIMO = 5 * 1024 * 1024
LADO_MAXIMO = 1920
TAMANO_MINIATURA = (240, 240)
Image.MAX_IMAGE_PIXELS = 40_000_000
FORMATO_POR_MIME = {"image/jpeg": ("JPEG", "jpg"), "image/png": ("PNG", "png"), "image/webp": ("WEBP", "webp")}


def detectar_mime_real(cabecera):
    if cabecera[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if cabecera[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(archivo):
    """1) extensión  2) MIME declarado  3) MIME real por firma binaria  4) Pillow la abre."""
    nombre = archivo.filename or "archivo"
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in EXTENSIONES:
        raise ErrorRegla(f"«{nombre}»: solo se permiten imágenes JPG, PNG o WEBP.")
    if (archivo.mimetype or "").lower() not in MIME_PERMITIDOS:
        raise ErrorRegla(f"«{nombre}»: el tipo de archivo no es una imagen permitida.")
    contenido = archivo.stream.read(TAMANO_MAXIMO + 1)
    if not contenido:
        raise ErrorRegla(f"«{nombre}»: el archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ErrorRegla(f"«{nombre}»: supera el máximo de 5 MB.")
    mime_real = detectar_mime_real(contenido[:12])
    if mime_real is None:
        raise ErrorRegla(f"«{nombre}»: el contenido no es una imagen real.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenido)) as img:
                img.verify()
                formato = img.format
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError):
        raise ErrorRegla(f"«{nombre}»: la imagen está dañada o es demasiado grande.")
    if FORMATO_POR_MIME[mime_real][0] != formato:
        raise ErrorRegla(f"«{nombre}»: el contenido no coincide con el tipo de imagen.")
    return {"nombre_original": nombre[-255:], "contenido": contenido, "mime_type": mime_real}


def _a_rgb(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert("RGB")


def ruta_miniatura(ruta):
    return ruta.rsplit(".", 1)[0] + "_min.jpg"


def guardar_foto(foto, empresa_codigo, ticket_id):
    """Guarda la imagen (sin EXIF, máx. 1920 px) y su miniatura en uploads/<empresa>/<ticket>/."""
    relativa = f"uploads/{empresa_codigo}/{ticket_id}"
    carpeta = os.path.join(config.BASE_DIR, *relativa.split("/"))
    os.makedirs(carpeta, exist_ok=True)
    mime = foto["mime_type"]
    formato, extension = FORMATO_POR_MIME[mime]
    base = uuid.uuid4().hex
    with Image.open(io.BytesIO(foto["contenido"])) as original:
        img = ImageOps.exif_transpose(original)
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
        destino = os.path.join(carpeta, f"{base}.{extension}")
        if formato == "JPEG":
            _a_rgb(img).save(destino, "JPEG", quality=85, optimize=True)
        elif formato == "PNG":
            img.save(destino, "PNG", optimize=True)
        else:
            img.save(destino, "WEBP", quality=85)
        if os.path.getsize(destino) > TAMANO_MAXIMO:
            os.remove(destino)
            mime, extension = "image/jpeg", "jpg"
            destino = os.path.join(carpeta, f"{base}.jpg")
            _a_rgb(img).save(destino, "JPEG", quality=80, optimize=True)
        ImageOps.fit(_a_rgb(img), TAMANO_MINIATURA, Image.Resampling.LANCZOS).save(
            os.path.join(carpeta, f"{base}_min.jpg"), "JPEG", quality=80
        )
    nombre_archivo = f"{base}.{extension}"
    return {
        "nombre_original": foto["nombre_original"],
        "nombre_archivo": nombre_archivo,
        "ruta": f"{relativa}/{nombre_archivo}",
        "mime_type": mime,
        "tamano_bytes": os.path.getsize(destino),
    }


def borrar_archivos(rutas):
    for ruta in rutas:
        for archivo in (ruta, ruta_miniatura(ruta)):
            try:
                os.remove(os.path.join(config.BASE_DIR, *archivo.split("/")))
            except FileNotFoundError:
                pass


def borrar_carpeta_ticket(empresa_codigo, ticket_id):
    shutil.rmtree(os.path.join(config.UPLOAD_DIR, empresa_codigo, str(ticket_id)), ignore_errors=True)


def fotos_de_la_peticion():
    return [a for a in request.files.getlist("fotos") if a and a.filename]


def guardar_evidencias(cur, ticket, fotos, usuario_id, guardadas):
    cur.execute("SELECT orden FROM ticket_evidencias WHERE ticket_id = %s", (ticket["id"],))
    usados = {f["orden"] for f in cur.fetchall()}
    libres = [n for n in range(1, MAX_EVIDENCIAS + 1) if n not in usados]
    if len(fotos) > len(libres):
        raise ErrorRegla(f"El ticket ya tiene {len(usados)} foto(s). Solo puedes agregar {len(libres)} más.")
    for foto, orden in zip(fotos, libres):
        info = guardar_foto(foto, ticket["empresa_codigo"], ticket["id"])
        guardadas.append(info["ruta"])
        cur.execute(
            """INSERT INTO ticket_evidencias (ticket_id, orden, nombre_original, nombre_archivo, ruta,
                                             mime_type, tamano_bytes, subido_por, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (ticket["id"], orden, info["nombre_original"], info["nombre_archivo"], info["ruta"],
             info["mime_type"], info["tamano_bytes"], usuario_id, ahora()),
        )


# =====================================================================
#  Lógica de negocio (la usan la web y la API)
# =====================================================================
def validar_datos_ticket(datos):
    errores = {}
    asunto = (datos.get("asunto") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()
    if not 5 <= len(asunto) <= 150:
        errores["asunto"] = "El asunto debe tener entre 5 y 150 caracteres."
    if not 10 <= len(descripcion) <= 2000:
        errores["descripcion"] = "Describe el problema con al menos 10 caracteres (máx. 2000)."
    cats = catalogos()
    categoria_id = entero(datos.get("categoria_id"))
    if categoria_id not in {c["id"] for c in cats["categorias"]}:
        errores["categoria_id"] = "Selecciona una categoría."
    valor = str(datos.get("prioridad") or datos.get("prioridad_id") or "").strip()
    prioridad = next((p for p in cats["prioridades"] if valor in (p["nombre"], str(p["id"]))), None)
    if prioridad is None:
        errores["prioridad"] = "Elige la prioridad: Alta, Media o Baja."
    limpios = {"asunto": asunto, "descripcion": descripcion, "categoria_id": categoria_id,
               "prioridad_id": prioridad["id"] if prioridad else None,
               "sla_horas": prioridad["sla_horas"] if prioridad else None}
    return limpios, errores


def crear_ticket(usuario, datos, archivos):
    """Registra el ticket + fotos + historial + notificación. Devuelve el id."""
    if usuario["rol"] == "Superusuario":
        raise ErrorRegla("El superusuario no pertenece a una empresa y no registra tickets.")
    if len(archivos) > MAX_EVIDENCIAS:
        raise ErrorRegla(f"Puedes adjuntar como máximo {MAX_EVIDENCIAS} fotos.")
    fotos = [validar_foto(a) for a in archivos]     # se validan TODAS antes de guardar
    con = conexion()
    guardadas, ticket_id = [], None
    try:
        with con.cursor() as cur:
            # Correlativo propio de la empresa. FOR UPDATE evita números repetidos.
            cur.execute("SELECT ultimo_ticket, prefijo_ticket, codigo FROM empresas WHERE id = %s FOR UPDATE",
                        (usuario["empresa_id"],))
            empresa = cur.fetchone()
            numero = empresa["ultimo_ticket"] + 1
            cur.execute("UPDATE empresas SET ultimo_ticket = %s WHERE id = %s", (numero, usuario["empresa_id"]))
            momento = ahora()
            cur.execute(
                """INSERT INTO tickets (empresa_id, numero, area_id, solicitante_id, categoria_id, prioridad_id,
                                        asunto, descripcion, estado, fecha_limite, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Abierto', %s, %s, %s)""",
                (usuario["empresa_id"], numero, usuario["area_id"], usuario["id"], datos["categoria_id"],
                 datos["prioridad_id"], datos["asunto"], datos["descripcion"],
                 momento + timedelta(hours=datos["sla_horas"]), momento, momento),
            )
            ticket_id = cur.lastrowid
            ticket = {"id": ticket_id, "empresa_codigo": empresa["codigo"]}
            guardar_evidencias(cur, ticket, fotos, usuario["id"], guardadas)
            texto = "Ticket registrado."
            if fotos:
                texto = f"Ticket registrado. Se adjuntaron {len(fotos)} foto(s) de evidencia."
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_nuevo, comentario, created_at)
                   VALUES (%s, %s, 'CREACION', 'Abierto', %s, %s)""",
                (ticket_id, usuario["id"], texto, momento),
            )
            codigo = codigo_ticket(empresa["prefijo_ticket"], numero)
            notificar(cur, administradores_de(cur, usuario["empresa_id"]), "NUEVO_TICKET", ticket_id,
                      f"Nuevo ticket {codigo}", f"{datos['asunto']} · registrado por {usuario['nombre']}",
                      excluir=usuario["id"])
        con.commit()
        return ticket_id
    except Exception:
        con.rollback()
        if ticket_id:
            borrar_carpeta_ticket(usuario["empresa_codigo"], ticket_id)
        raise


def asignar_ticket(usuario, ticket, tecnico_id, comentario):
    if not permisos(usuario, ticket)["asignar"]:
        raise ErrorRegla("Solo el administrador puede asignar tickets abiertos.")
    tecnico = next((t for t in tecnicos_de(ticket["empresa_id"]) if t["id"] == tecnico_id), None)
    if tecnico is None:
        raise ErrorRegla("Elige un técnico activo de la misma empresa.")
    if tecnico_id == ticket["tecnico_id"]:
        raise ErrorRegla(f"El ticket ya está asignado a {tecnico['nombre']}.")
    comentario = (comentario or "").strip() or f"Asignado a {tecnico['nombre']}."
    con = conexion()
    try:
        with con.cursor() as cur:
            momento = ahora()
            cur.execute("UPDATE tickets SET tecnico_id = %s, updated_at = %s WHERE id = %s",
                        (tecnico_id, momento, ticket["id"]))
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, tecnico_anterior_id, tecnico_nuevo_id,
                                                 comentario, created_at)
                   VALUES (%s, %s, 'ASIGNACION', %s, %s, %s, %s)""",
                (ticket["id"], usuario["id"], ticket["tecnico_id"], tecnico_id, comentario[:2000], momento),
            )
            notificar(cur, [tecnico_id], "ASIGNACION", ticket["id"],
                      f"Se te asignó el ticket {ticket['codigo']}", ticket["asunto"], excluir=usuario["id"])
            notificar(cur, [ticket["solicitante_id"]], "ASIGNACION", ticket["id"],
                      f"{ticket['codigo']} fue asignado a {tecnico['nombre']}", ticket["asunto"], excluir=usuario["id"])
        con.commit()
    except Exception:
        con.rollback()
        raise
    return tecnico


def cambiar_estado(usuario, ticket, nuevo, comentario):
    comentario = (comentario or "").strip()
    if nuevo not in ESTADOS:
        raise ErrorRegla("Estado no válido.")
    if nuevo == ticket["estado"]:
        raise ErrorRegla(f"El ticket ya está «{nuevo}».")
    if nuevo not in estados_permitidos(usuario, ticket):
        if nuevo == "En proceso" and not ticket["tecnico_id"]:
            raise ErrorRegla("Primero asigna un técnico para pasar el ticket a «En proceso».")
        raise ErrorRegla(f"No puedes pasar este ticket de «{ticket['estado']}» a «{nuevo}».")
    if len(comentario) < 3:
        raise ErrorRegla("Escribe un comentario para poder guardar el cambio.")
    momento = ahora()
    # Fechas de resolución y cierre (para medir el SLA)
    resolucion, cierre = ticket["fecha_resolucion"], ticket["fecha_cierre"]
    if nuevo == "Resuelto":
        resolucion, cierre = momento, None
    elif nuevo == "Cerrado":
        resolucion, cierre = resolucion or momento, momento
    else:  # se reabre o vuelve a abierto
        resolucion, cierre = None, None
    con = conexion()
    try:
        with con.cursor() as cur:
            # UPDATE validado: solo cambia si el estado no fue modificado por otra persona
            cur.execute(
                """UPDATE tickets SET estado = %s, fecha_resolucion = %s, fecha_cierre = %s, updated_at = %s
                    WHERE id = %s AND estado = %s""",
                (nuevo, resolucion, cierre, momento, ticket["id"], ticket["estado"]),
            )
            if cur.rowcount != 1:
                raise ErrorRegla("Alguien cambió este ticket hace un momento. Recarga la página.")
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo,
                                                 comentario, created_at)
                   VALUES (%s, %s, 'CAMBIO_ESTADO', %s, %s, %s, %s)""",
                (ticket["id"], usuario["id"], ticket["estado"], nuevo, comentario[:2000], momento),
            )
            notificar(cur, [ticket["solicitante_id"], ticket["tecnico_id"]], "CAMBIO_ESTADO", ticket["id"],
                      f"{ticket['codigo']} cambió a {nuevo}", f"{ticket['asunto']} · por {usuario['nombre']}",
                      excluir=usuario["id"])
        con.commit()
    except Exception:
        con.rollback()
        raise


def comentar(usuario, ticket, comentario):
    comentario = (comentario or "").strip()
    if not permisos(usuario, ticket)["comentar"]:
        raise ErrorRegla("El ticket está cerrado y ya no admite comentarios.")
    if len(comentario) < 3:
        raise ErrorRegla("El comentario está vacío.")
    con = conexion()
    try:
        with con.cursor() as cur:
            momento = ahora()
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                   VALUES (%s, %s, 'COMENTARIO', %s, %s)""",
                (ticket["id"], usuario["id"], comentario[:2000], momento),
            )
            destinatarios = [ticket["solicitante_id"], ticket["tecnico_id"]]
            if not ticket["tecnico_id"]:
                destinatarios += administradores_de(cur, ticket["empresa_id"])
            notificar(cur, destinatarios, "COMENTARIO", ticket["id"], f"Nuevo comentario en {ticket['codigo']}",
                      f"{ticket['asunto']} · {usuario['nombre']}", excluir=usuario["id"])
        con.commit()
    except Exception:
        con.rollback()
        raise


def eliminar_ticket(usuario, ticket):
    if not permisos(usuario, ticket)["eliminar"]:
        raise ErrorRegla("Este ticket ya está en atención y no se puede eliminar.")
    con = conexion()
    try:
        with con.cursor() as cur:
            for tabla, columna in (("notificaciones", "referencia_ticket"), ("ticket_historial", "ticket_id"),
                                   ("ticket_evidencias", "ticket_id"), ("tickets", "id")):
                cur.execute(f"DELETE FROM {tabla} WHERE {columna} = %s", (ticket["id"],))
        con.commit()
    except Exception:
        con.rollback()
        raise
    borrar_carpeta_ticket(ticket["empresa_codigo"], ticket["id"])


# =====================================================================
#  Errores
# =====================================================================
@tickets_bp.errorhandler(ErrorRegla)
def _error_regla(error):
    if request.path.startswith("/api"):
        return jsonify(status=-1, ok=False, error=str(error), message=str(error)), 400
    flash(str(error), "error")
    return redirect(_volver())


def _volver():
    """Tras un error, vuelve al detalle del ticket (o a la página anterior)."""
    ticket_id = (request.view_args or {}).get("ticket_id")
    if ticket_id:
        return url_for("tickets.detalle", ticket_id=ticket_id)
    return request.referrer or url_for("tickets.listado")


@tickets_bp.errorhandler(pymysql.MySQLError)
def _error_mysql(error):
    current_app.logger.exception("Error de base de datos en tickets")
    mensaje = "No se pudo guardar en la base de datos. Revisa los datos e inténtalo otra vez."
    if request.path.startswith("/api"):
        return jsonify(status=-1, ok=False, error=mensaje, message=mensaje), 500
    flash(mensaje, "error")
    return redirect(_volver())


# =====================================================================
#  Páginas
# =====================================================================
@tickets_bp.get("/tickets")
@login_requerido
def listado():
    filtros = {
        "q": (request.args.get("q") or "").strip()[:60],
        "estado": request.args.get("estado") or "",
        "prioridad": request.args.get("prioridad") or "",
        "tecnico": request.args.get("tecnico") or "",
        "urgentes": request.args.get("urgentes") == "1",
    }
    empresa_id = empresa_filtro()
    tickets = buscar_tickets(g.usuario, filtros, empresa_id)
    todos = buscar_tickets(g.usuario, {}, empresa_id) if any(filtros.values()) else tickets
    vencidos = sum(1 for t in todos if t["semaforo"] == "rojo")
    por_vencer = sum(1 for t in todos if t["semaforo"] == "amarillo")

    total = len(tickets)
    paginas = max(1, math.ceil(total / POR_PAGINA))
    pagina = min(max(entero(request.args.get("pagina")) or 1, 1), paginas)
    visibles = tickets[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]

    tecnicos = []
    if g.usuario["rol"] == "Administrador":
        tecnicos = tecnicos_de(g.usuario["empresa_id"])
    elif es_super() and empresa_id:
        tecnicos = tecnicos_de(empresa_id)
    return render_template(
        "tickets.html", tickets=visibles, total=total, pagina=pagina, paginas=paginas,
        desde=(pagina - 1) * POR_PAGINA + 1 if total else 0, hasta=min(pagina * POR_PAGINA, total),
        filtros=filtros, vencidos=vencidos, por_vencer=por_vencer, tecnicos=tecnicos,
        prioridades=catalogos()["prioridades"], estados=ESTADOS,
    )


@tickets_bp.route("/tickets/nuevo", methods=["GET", "POST"])
@roles_requeridos("Administrador", "Técnico", "Solicitante")
def nuevo():
    errores, datos_form = {}, {}
    if request.method == "POST":
        datos_form = request.form
        datos, errores = validar_datos_ticket(request.form)
        archivos = fotos_de_la_peticion()
        if not errores:
            try:
                ticket_id = crear_ticket(g.usuario, datos, archivos)
            except ErrorRegla as e:
                errores["fotos"] = str(e)
            else:
                ticket = obtener_ticket(ticket_id, g.usuario) or {"codigo": "", "id": ticket_id}
                flash(f"Ticket {ticket['codigo']} registrado. Te avisaremos cuando cambie de estado.", "ok")
                if ticket.get("codigo"):
                    return redirect(url_for("tickets.detalle", ticket_id=ticket_id))
                return redirect(url_for("tickets.listado"))
        flash("Revisa los campos marcados.", "error")
    return render_template("ticket_nuevo.html", errores=errores, form=datos_form,
                           ahora=ahora(), max_mb=TAMANO_MAXIMO // (1024 * 1024), **catalogos()), (400 if errores else 200)


@tickets_bp.get("/tickets/<int:ticket_id>")
@login_requerido
def detalle(ticket_id):
    ticket = ticket_o_404(ticket_id)
    return render_template(
        "ticket_detalle.html", t=ticket, evidencias=evidencias_de(ticket_id),
        historial=historial_de(ticket_id), permisos=permisos(g.usuario, ticket),
        tecnicos=tecnicos_de(ticket["empresa_id"]) if es_gestor(g.usuario, ticket) else [],
        max_evidencias=MAX_EVIDENCIAS,
    )


@tickets_bp.post("/tickets/<int:ticket_id>/asignar")
@login_requerido
def asignar(ticket_id):
    ticket = ticket_o_404(ticket_id)
    tecnico = asignar_ticket(g.usuario, ticket, entero(request.form.get("tecnico_id")), request.form.get("comentario"))
    flash(f"Ticket asignado a {tecnico['nombre']}.", "ok")
    return redirect(url_for("tickets.detalle", ticket_id=ticket_id))


@tickets_bp.post("/tickets/<int:ticket_id>/estado")
@login_requerido
def estado(ticket_id):
    ticket = ticket_o_404(ticket_id)
    nuevo_estado = request.form.get("estado", "")
    cambiar_estado(g.usuario, ticket, nuevo_estado, request.form.get("comentario"))
    flash(f"El ticket pasó a «{nuevo_estado}».", "ok")
    return redirect(url_for("tickets.detalle", ticket_id=ticket_id))


@tickets_bp.post("/tickets/<int:ticket_id>/comentar")
@login_requerido
def comentar_web(ticket_id):
    ticket = ticket_o_404(ticket_id)
    comentar(g.usuario, ticket, request.form.get("comentario"))
    flash("Comentario agregado.", "ok")
    return redirect(url_for("tickets.detalle", ticket_id=ticket_id) + "#linea-tiempo")


@tickets_bp.post("/tickets/<int:ticket_id>/evidencias")
@login_requerido
def agregar_evidencias(ticket_id):
    ticket = ticket_o_404(ticket_id)
    if not permisos(g.usuario, ticket)["adjuntar"]:
        raise ErrorRegla("No puedes adjuntar más fotos a este ticket.")
    archivos = fotos_de_la_peticion()
    if not archivos:
        raise ErrorRegla("Selecciona al menos una foto.")
    fotos = [validar_foto(a) for a in archivos]
    con, guardadas = conexion(), []
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM tickets WHERE id = %s FOR UPDATE", (ticket_id,))
            guardar_evidencias(cur, ticket, fotos, g.usuario["id"], guardadas)
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                   VALUES (%s, %s, 'COMENTARIO', %s, %s)""",
                (ticket_id, g.usuario["id"], f"Se adjuntaron {len(fotos)} foto(s) de evidencia.", ahora()),
            )
        con.commit()
    except Exception:
        con.rollback()
        borrar_archivos(guardadas)
        raise
    flash(f"{len(fotos)} foto(s) agregada(s).", "ok")
    return redirect(url_for("tickets.detalle", ticket_id=ticket_id))


@tickets_bp.post("/tickets/<int:ticket_id>/eliminar")
@login_requerido
def eliminar(ticket_id):
    ticket = ticket_o_404(ticket_id)
    eliminar_ticket(g.usuario, ticket)
    flash(f"Ticket {ticket['codigo']} eliminado.", "ok")
    return redirect(url_for("tickets.listado"))


@tickets_bp.get("/evidencias/<int:evidencia_id>/<any(miniatura, imagen):tipo>")
@login_requerido
def ver_evidencia(evidencia_id, tipo):
    """Las fotos no son públicas: se sirven solo si el usuario puede ver el ticket."""
    ev = consultar("SELECT ticket_id, ruta, mime_type FROM ticket_evidencias WHERE id = %s", (evidencia_id,), uno=True)
    if not ev or not obtener_ticket(ev["ticket_id"], g.usuario):
        abort(404)
    ruta, mime = (ruta_miniatura(ev["ruta"]), "image/jpeg") if tipo == "miniatura" else (ev["ruta"], ev["mime_type"])
    respuesta = send_from_directory(config.BASE_DIR, ruta, mimetype=mime, max_age=600)
    respuesta.headers["Cache-Control"] = "private, max-age=600"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


# =====================================================================
#  API REST (JSON + JWT en el header Authorization)
# =====================================================================
def ticket_json(t, detalle=False):
    datos = {
        "id": t["id"], "codigo": t["codigo"], "asunto": t["asunto"], "empresa": t["empresa"],
        "area": t["area"], "categoria": t["categoria"], "prioridad": t["prioridad"], "estado": t["estado"],
        "solicitante": t["solicitante"], "tecnico": t["tecnico"], "created_at": fecha_iso(t["created_at"]),
        "fecha_limite": fecha_iso(t["fecha_limite"]), "semaforo": t["semaforo"], "sla": t["sla_texto"],
        "minutos_restantes": t["minutos_restantes"], "urgencia": t["urgencia"],
        "total_evidencias": t["total_evidencias"],
    }
    if detalle:
        datos["descripcion"] = t["descripcion"]
        datos["evidencias"] = [
            {"id": e["id"], "orden": e["orden"], "nombre": e["nombre_original"],
             "imagen_url": url_for("tickets.ver_evidencia", evidencia_id=e["id"], tipo="imagen"),
             "miniatura_url": url_for("tickets.ver_evidencia", evidencia_id=e["id"], tipo="miniatura")}
            for e in evidencias_de(t["id"])
        ]
        datos["historial"] = [
            {"tipo": h["tipo"], "titulo": h["titulo"], "comentario": h["comentario"], "usuario": h["usuario"],
             "created_at": fecha_iso(h["created_at"])}
            for h in historial_de(t["id"])
        ]
    return datos


@tickets_bp.get("/api/tickets")
@login_requerido
def api_listar():
    filtros = {k: request.args.get(k) for k in ("q", "estado", "prioridad", "tecnico")}
    filtros["urgentes"] = request.args.get("urgentes") == "1"
    empresa_id = entero(request.args.get("empresa_id")) if es_super() else None
    tickets = buscar_tickets(g.usuario, filtros, empresa_id)
    return jsonify(status=1, total=len(tickets), data=[ticket_json(t) for t in tickets])


@tickets_bp.get("/api/tickets/<int:ticket_id>")
@login_requerido
def api_detalle(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    return jsonify(status=1, data=ticket_json(ticket, detalle=True))


@tickets_bp.post("/api/tickets")
@login_requerido
def api_crear():
    datos_in = request.form if request.form else (request.get_json(silent=True) or {})
    datos, errores = validar_datos_ticket(datos_in)
    if errores:
        return jsonify(status=-1, message="Revisa los campos.", errores=errores), 400
    ticket_id = crear_ticket(g.usuario, datos, fotos_de_la_peticion())
    return jsonify(status=1, message="Ticket registrado",
                   data=ticket_json(obtener_ticket(ticket_id, g.usuario), True)), 201


@tickets_bp.post("/api/tickets/<int:ticket_id>/asignar")
@login_requerido
def api_asignar(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    datos = request.get_json(silent=True) or request.form
    asignar_ticket(g.usuario, ticket, entero(datos.get("tecnico_id")), datos.get("comentario"))
    return jsonify(status=1, message="Ticket asignado", data=ticket_json(obtener_ticket(ticket_id, g.usuario)))


@tickets_bp.route("/api/tickets/<int:ticket_id>/estado", methods=["POST", "PUT"])
@login_requerido
def api_estado(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    datos = request.get_json(silent=True) or request.form
    cambiar_estado(g.usuario, ticket, datos.get("estado", ""), datos.get("comentario"))
    return jsonify(status=1, message="Estado actualizado", data=ticket_json(obtener_ticket(ticket_id, g.usuario)))


@tickets_bp.post("/api/tickets/<int:ticket_id>/comentarios")
@login_requerido
def api_comentar(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    datos = request.get_json(silent=True) or request.form
    comentar(g.usuario, ticket, datos.get("comentario"))
    return jsonify(status=1, message="Comentario agregado"), 201


@tickets_bp.get("/api/tickets/<int:ticket_id>/historial")
@login_requerido
def api_historial(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    return jsonify(status=1, data=ticket_json(ticket, True)["historial"])


@tickets_bp.delete("/api/tickets/<int:ticket_id>")
@login_requerido
def api_eliminar(ticket_id):
    ticket = obtener_ticket(ticket_id, g.usuario)
    if not ticket:
        return jsonify(status=-1, message="El ticket no existe o no tienes acceso."), 404
    eliminar_ticket(g.usuario, ticket)
    return jsonify(status=1, message=f"Ticket {ticket['codigo']} eliminado")
