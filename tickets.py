import io
import os
import shutil
import uuid
import warnings
from datetime import datetime
from functools import wraps

import pymysql
from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    request,
    send_from_directory,
    url_for,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

from auth import ROL_SUPER, empresa_actual
from chat_realtime import emitir_comentario_ticket
from db import conexion
from vistas import V_TICKET_TIMELINE, V_TICKETS, aplicar_sla, aplicar_sla_lista

tickets_bp = Blueprint("tickets", __name__)

class Catalogo:
    
    @staticmethod
    def categorias():
        with conexion().cursor() as cur:
            cur.execute(
                "SELECT id, nombre FROM categorias WHERE activo = 1 ORDER BY nombre"
            )
            return cur.fetchall()

    @staticmethod
    def prioridades():
        with conexion().cursor() as cur:
            cur.execute(
                "SELECT id, nombre, sla_horas FROM prioridades ORDER BY nivel DESC"
            )
            return cur.fetchall()

    @staticmethod
    def areas(empresa_id):
        with conexion().cursor() as cur:
            cur.execute(
                "SELECT id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre",
                (empresa_id,),
            )
            return cur.fetchall()


class ErrorRegla(Exception):
    pass


class Ticket:
    ESTADOS = ("Abierto", "En proceso", "Resuelto", "Cerrado")

    @staticmethod
    def validar(datos, usuario):

        errores = {}
        asunto = (datos.get("asunto") or "").strip()
        descripcion = (datos.get("descripcion") or "").strip()

        if len(asunto) < 5:
            errores["asunto"] = "El asunto debe tener al menos 5 caracteres."
        elif len(asunto) > 150:
            errores["asunto"] = "El asunto no puede superar 150 caracteres."
        if len(descripcion) < 10:
            errores["descripcion"] = "Describe el problema (mínimo 10 caracteres)."
        elif len(descripcion) > 2000:
            errores["descripcion"] = "La descripción no puede superar 2000 caracteres."

        categorias = {c["id"] for c in Catalogo.categorias()}
        categoria_id = _entero(datos.get("categoria_id"))
        if categoria_id not in categorias:
            errores["categoria_id"] = "Selecciona una categoría válida."

        prioridades = Catalogo.prioridades()
        valor = str(datos.get("prioridad") or datos.get("prioridad_id") or "").strip()
        prioridad_id = next(
            (p["id"] for p in prioridades if valor in (p["nombre"], str(p["id"]))), None
        )
        if prioridad_id is None:
            errores["prioridad"] = "La prioridad debe ser Alta, Media o Baja."

        area_id = _entero(datos.get("area_id")) or usuario["area_id"]
        if area_id is not None and area_id not in {
            a["id"] for a in Catalogo.areas(usuario["empresa_id"])
        }:
            errores["area_id"] = "Selecciona un área válida."

        limpios = {
            "asunto": asunto,
            "descripcion": descripcion,
            "categoria_id": categoria_id,
            "prioridad_id": prioridad_id,
            "area_id": area_id,
        }
        return limpios, errores

    @staticmethod
    def _horas_sla(cur, prioridad_id):
        cur.execute("SELECT sla_horas FROM prioridades WHERE id = %s", (prioridad_id,))
        fila = cur.fetchone()
        if fila is None:
            raise ErrorRegla("La prioridad no existe.")
        return fila["sla_horas"]

    @staticmethod
    def crear(cur, datos, solicitante_id, empresa_id):
        cur.execute(
            "SELECT empresa_id, area_id, activo, nombre FROM users WHERE id = %s",
            (solicitante_id,),
        )
        solicitante = cur.fetchone()
        if solicitante is None:
            raise ErrorRegla("El solicitante no existe.")
        if not solicitante["activo"]:
            raise ErrorRegla("El solicitante está inactivo.")
        empresa_id = solicitante["empresa_id"]
        area_id = datos["area_id"] or solicitante["area_id"]

        cur.execute(
            "SELECT ultimo_ticket, prefijo_ticket FROM empresas WHERE id = %s FOR UPDATE",
            (empresa_id,),
        )
        empresa = cur.fetchone()
        numero = empresa["ultimo_ticket"] + 1
        cur.execute(
            "UPDATE empresas SET ultimo_ticket = %s WHERE id = %s", (numero, empresa_id)
        )

        horas = Ticket._horas_sla(cur, datos["prioridad_id"])

        cur.execute(
            """INSERT INTO tickets
                 (empresa_id, numero, area_id, solicitante_id, categoria_id, prioridad_id,
                  asunto, descripcion, estado, created_at, fecha_limite)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Abierto', NOW(), NOW() + INTERVAL %s HOUR)""",
            (
                empresa_id,
                numero,
                area_id,
                solicitante_id,
                datos["categoria_id"],
                datos["prioridad_id"],
                datos["asunto"],
                datos["descripcion"],
                horas,
            ),
        )
        ticket_id = cur.lastrowid

        cur.execute(
            """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_nuevo, comentario, created_at)
               SELECT id, solicitante_id, 'CREACION', 'Abierto', 'Ticket registrado.', created_at
                 FROM tickets WHERE id = %s""",
            (ticket_id,),
        )

        codigo = f"{empresa['prefijo_ticket']}-{numero:04d}"
        cur.execute(
            """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
               SELECT id, 'NUEVO_TICKET', %s, %s, %s
                 FROM users
                WHERE empresa_id = %s AND rol = 'Administrador' AND activo = 1 AND id <> %s""",
            (
                ticket_id,
                f"Nuevo ticket {codigo}",
                f"{datos['asunto']} · registrado por {solicitante['nombre']}"[:255],
                empresa_id,
                solicitante_id,
            ),
        )
        return ticket_id

    @staticmethod
    def actualizar(cur, ticket_id, datos, empresa_id):

        cur.execute(
            "SELECT estado, prioridad_id FROM tickets WHERE id = %s AND empresa_id = %s FOR UPDATE",
            (ticket_id, empresa_id),
        )
        actual = cur.fetchone()
        if actual is None:
            raise ErrorRegla("El ticket no existe.")
        if actual["estado"] == "Cerrado":
            raise ErrorRegla("Un ticket cerrado no se puede modificar.")

        cur.execute(
            """UPDATE tickets
                  SET asunto = %s, descripcion = %s, categoria_id = %s, prioridad_id = %s, area_id = %s
                WHERE id = %s AND empresa_id = %s""",
            (
                datos["asunto"],
                datos["descripcion"],
                datos["categoria_id"],
                datos["prioridad_id"],
                datos["area_id"],
                ticket_id,
                empresa_id,
            ),
        )
        if datos["prioridad_id"] != actual["prioridad_id"]:
            horas = Ticket._horas_sla(cur, datos["prioridad_id"])
            cur.execute(
                "UPDATE tickets SET fecha_limite = created_at + INTERVAL %s HOUR WHERE id = %s",
                (horas, ticket_id),
            )
            
    TRANSICIONES = {  # noqa: RUF012
        "Abierto": ("En proceso",),
        "En proceso": ("Resuelto",),
        "Resuelto": ("Cerrado", "En proceso"),
        "Cerrado": (),
    }
    MIN_COMENTARIO = 10
    MAX_COMENTARIO = 500

    @staticmethod
    def validar_cambio_estado(estado_actual, estado_nuevo, tecnico_id, comentario):
        if estado_nuevo not in Ticket.ESTADOS:
            raise ErrorRegla("El estado indicado no existe.")
        permitidos = Ticket.TRANSICIONES[estado_actual]
        if estado_nuevo not in permitidos:
            if not permitidos:
                raise ErrorRegla(
                    "El ticket está cerrado; ya no admite cambios de estado."
                )
            raise ErrorRegla(
                f"No se puede pasar de «{estado_actual}» a «{estado_nuevo}». "
                f"Desde «{estado_actual}» solo se permite: {', '.join(permitidos)}."
            )
        if estado_nuevo == "En proceso" and not tecnico_id:
            raise ErrorRegla(
                "Primero asigna un técnico para pasar el ticket a «En proceso»."
            )
        if len(comentario) < Ticket.MIN_COMENTARIO:
            raise ErrorRegla(
                f"El comentario es obligatorio (mínimo {Ticket.MIN_COMENTARIO} caracteres)."
            )

    @staticmethod
    def actualizar_gestion(cur, ticket_id, datos, usuario):
        empresa_id = usuario["empresa_id"]

        cur.execute(
            """
            SELECT t.estado, t.prioridad_id, t.categoria_id, t.tecnico_id, t.solicitante_id
            FROM tickets t
            WHERE t.id = %s AND t.empresa_id = %s FOR UPDATE
        """,
            (ticket_id, empresa_id),
        )

        actual = cur.fetchone()
        if not actual:
            raise ErrorRegla("El ticket no existe.")

        estado_nuevo = datos.get("estado") or actual["estado"]
        comentario = (datos.get("comentario") or "").strip()
        if len(comentario) > Ticket.MAX_COMENTARIO:
            raise ErrorRegla(
                f"El comentario no puede superar los {Ticket.MAX_COMENTARIO} caracteres."
            )

        cur.execute(
            "SELECT id FROM prioridades WHERE nombre = %s", (datos.get("prioridad"),)
        )
        prio = cur.fetchone()
        prioridad_id_nueva = prio["id"] if prio else actual["prioridad_id"]

        cur.execute(
            "SELECT id FROM categorias WHERE nombre = %s", (datos.get("categoria"),)
        )
        cat = cur.fetchone()
        categoria_id_nueva = cat["id"] if cat else actual["categoria_id"]

        tecnico_id_nuevo = actual["tecnico_id"]
        tecnico_nombre = None
        if "tecnico" in datos:
            if datos["tecnico"] in (None, "", "Sin asignar"):
                if actual["tecnico_id"]:
                    raise ErrorRegla(
                        "Un ticket asignado no puede quedar sin técnico. Elige otro técnico para reasignarlo."
                    )
            else:
                cur.execute(
                    """SELECT id, nombre FROM users
                        WHERE nombre = %s AND empresa_id = %s AND rol = %s AND activo = 1""",
                    (datos["tecnico"], empresa_id, ROL_TECNICO),
                )
                tec = cur.fetchone()
                if not tec:
                    raise ErrorRegla(
                        "El técnico elegido no existe o no está activo en tu empresa."
                    )
                tecnico_id_nuevo = tec["id"]
                tecnico_nombre = tec["nombre"]

        cambia_estado = estado_nuevo != actual["estado"]
        cambia_tecnico = tecnico_id_nuevo != actual["tecnico_id"]

        cambia_prioridad = prioridad_id_nueva != actual["prioridad_id"]
        cambia_categoria = categoria_id_nueva != actual["categoria_id"]

        if usuario["rol"] == ROL_SOLICITANTE:
            confirma_o_reabre = (
                cambia_estado
                and not cambia_tecnico
                and actual["solicitante_id"] == usuario["id"]
                and actual["estado"] == "Resuelto"
                and estado_nuevo in ("Cerrado", "En proceso")
            )
            if cambia_tecnico or (cambia_estado and not confirma_o_reabre):
                raise ErrorRegla(
                    "Solo el administrador o el técnico asignado pueden cambiar el estado o el técnico. "
                    "Tú puedes cerrar o reabrir tu ticket cuando esté «Resuelto»."
                )

        if (cambia_prioridad or cambia_categoria) and not (
            usuario["rol"] == ROL_ADMIN
            or (usuario["rol"] == ROL_TECNICO and actual["tecnico_id"] == usuario["id"])
        ):
            raise ErrorRegla(
                "Solo el administrador o el técnico asignado pueden cambiar la prioridad o la categoría."
            )
        if cambia_tecnico:
            if usuario["rol"] != ROL_ADMIN:
                raise ErrorRegla(
                    "Solo el administrador puede asignar o reasignar técnicos."
                )
            if actual["estado"] in ("Resuelto", "Cerrado"):
                raise ErrorRegla("No se puede reasignar un ticket resuelto o cerrado.")
        if (
            cambia_estado
            and usuario["rol"] == ROL_TECNICO
            and actual["tecnico_id"] != usuario["id"]
        ):
            raise ErrorRegla(
                "Solo el técnico asignado puede cambiar el estado de este ticket."
            )

        if cambia_estado:
            Ticket.validar_cambio_estado(
                actual["estado"], estado_nuevo, tecnico_id_nuevo, comentario
            )

        cur.execute(
            """
            UPDATE tickets 
            SET estado = %s, prioridad_id = %s, categoria_id = %s, tecnico_id = %s 
            WHERE id = %s AND empresa_id = %s
        """,
            (
                estado_nuevo,
                prioridad_id_nueva,
                categoria_id_nueva,
                tecnico_id_nuevo,
                ticket_id,
                empresa_id,
            ),
        )

        if cambia_prioridad or cambia_categoria:
            cur.execute(
                """SELECT (SELECT nombre FROM prioridades WHERE id = %s) AS p_ant,
                          (SELECT nombre FROM prioridades WHERE id = %s) AS p_new,
                          (SELECT nombre FROM categorias WHERE id = %s) AS c_ant,
                          (SELECT nombre FROM categorias WHERE id = %s) AS c_new""",
                (
                    actual["prioridad_id"],
                    prioridad_id_nueva,
                    actual["categoria_id"],
                    categoria_id_nueva,
                ),
            )
            n = cur.fetchone()
            partes = []
            if cambia_prioridad:
                partes.append(
                    f"Prioridad: {n['p_ant']} → {n['p_new']} (el plazo SLA se recalculó)"
                )
            if cambia_categoria:
                partes.append(f"Categoría: {n['c_ant']} → {n['c_new']}")
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                   VALUES (%s, %s, 'COMENTARIO', %s, NOW())""",
                (ticket_id, usuario["id"], ". ".join(partes) + "."),
            )
        if cambia_prioridad:
            horas = Ticket._horas_sla(cur, prioridad_id_nueva)
            cur.execute(
                "UPDATE tickets SET fecha_limite = created_at + INTERVAL %s HOUR WHERE id = %s",
                (horas, ticket_id),
            )

        if cambia_estado:
            if estado_nuevo == "Resuelto":
                cur.execute(
                    "UPDATE tickets SET fecha_resolucion = NOW() WHERE id = %s",
                    (ticket_id,),
                )
            elif estado_nuevo == "Cerrado":
                cur.execute(
                    """UPDATE tickets SET fecha_cierre = NOW(),
                              fecha_resolucion = COALESCE(fecha_resolucion, NOW())
                        WHERE id = %s""",
                    (ticket_id,),
                )
            elif estado_nuevo == "En proceso" and actual["estado"] == "Resuelto":
                cur.execute(
                    "UPDATE tickets SET fecha_resolucion = NULL WHERE id = %s",
                    (ticket_id,),
                )

        if cambia_tecnico:
            cur.execute(
                """
                INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, tecnico_anterior_id, tecnico_nuevo_id, comentario, created_at)
                VALUES (%s, %s, 'ASIGNACION', %s, %s, %s, NOW())
            """,
                (
                    ticket_id,
                    usuario["id"],
                    actual["tecnico_id"],
                    tecnico_id_nuevo,
                    comentario or f"Ticket asignado a {tecnico_nombre}.",
                ),
            )

        if cambia_estado:
            cur.execute(
                """
                INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, comentario, created_at)
                VALUES (%s, %s, 'CAMBIO_ESTADO', %s, %s, %s, NOW())
            """,
                (
                    ticket_id,
                    usuario["id"],
                    actual["estado"],
                    estado_nuevo,
                    comentario,
                ),
            )

        if cambia_tecnico or cambia_estado:
            cur.execute(
                f"SELECT codigo, asunto, solicitante_id, tecnico_id FROM {V_TICKETS} AS v WHERE v.id = %s",
                (ticket_id,),
            )
            info = cur.fetchone()
            if cambia_tecnico and tecnico_id_nuevo != usuario["id"]:
                cur.execute(
                    """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                       VALUES (%s, 'ASIGNACION', %s, %s, %s)""",
                    (
                        tecnico_id_nuevo,
                        ticket_id,
                        f"Se te asignó el ticket {info['codigo']}",
                        f"{info['asunto']} · asignado por {usuario['nombre']}"[:255],
                    ),
                )
            if (
                cambia_estado
                and info["tecnico_id"]
                and info["tecnico_id"] != usuario["id"]
                and not cambia_tecnico
            ):
                cur.execute(
                    """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                       VALUES (%s, 'CAMBIO_ESTADO', %s, %s, %s)""",
                    (
                        info["tecnico_id"],
                        ticket_id,
                        f"{info['codigo']} pasó a «{estado_nuevo}»",
                        f"{usuario['nombre']}: {comentario}"[:255],
                    ),
                )
            if cambia_estado and info["solicitante_id"] != usuario["id"]:
                cur.execute(
                    """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                       VALUES (%s, 'CAMBIO_ESTADO', %s, %s, %s)""",
                    (
                        info["solicitante_id"],
                        ticket_id,
                        f"Tu ticket {info['codigo']} pasó a «{estado_nuevo}»",
                        f"{usuario['nombre']}: {comentario}"[:255],
                    ),
                )

        return {
            "tecnico_avisar": tecnico_id_nuevo if cambia_tecnico else None,
            "reasignacion": bool(cambia_tecnico and actual["tecnico_id"]),
        }

    @staticmethod
    def eliminar(cur, ticket_id):
        cur.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))

    @staticmethod
    def bloquear(cur, ticket_id):
        cur.execute("SELECT id FROM tickets WHERE id = %s FOR UPDATE", (ticket_id,))
        return cur.fetchone() is not None

    @staticmethod
    def obtener(ticket_id, empresa_id):
        with conexion().cursor() as cur:
            cur.execute(
                f"SELECT * FROM {V_TICKETS} AS v WHERE v.id = %s AND v.empresa_id = %s",
                (ticket_id, empresa_id),
            )
            return aplicar_sla(cur.fetchone())

    @staticmethod
    def listar(usuario, filtros):
        condiciones, params = ["v.empresa_id = %s"], [usuario["empresa_id"]]

        if filtros.get("mios"):
            condiciones.append("(v.solicitante_id = %s OR v.tecnico_id = %s)")
            params.extend([usuario["id"], usuario["id"]])
        elif usuario["rol"] == ROL_SOLICITANTE:
            condiciones.append("v.solicitante_id = %s")
            params.append(usuario["id"])
        elif usuario["rol"] == ROL_TECNICO:
            condiciones.append("(v.tecnico_id = %s OR v.tecnico_id IS NULL)")
            params.append(usuario["id"])

        if filtros.get("estado") in Ticket.ESTADOS:
            condiciones.append("v.estado = %s")
            params.append(filtros["estado"])
        if filtros.get("prioridad"):
            condiciones.append("v.prioridad = %s")
            params.append(filtros["prioridad"])
        if filtros.get("q"):
            condiciones.append("(v.asunto LIKE %s OR v.codigo LIKE %s)")
            params.extend([f"%{filtros['q']}%", f"%{filtros['q']}%"])

        params.append(filtros.get("limite", 100))

        with conexion().cursor() as cur:
            cur.execute(
                f"""SELECT v.*,
                           (SELECT e.id FROM ticket_evidencias e
                             WHERE e.ticket_id = v.id ORDER BY e.orden LIMIT 1) AS primera_evidencia_id
                      FROM {V_TICKETS} v
                     WHERE {" AND ".join(condiciones)}
                     ORDER BY v.created_at DESC, v.id DESC
                     LIMIT %s""",
                params,
            )
            return aplicar_sla_lista(cur.fetchall())


class Evidencia:
    MAX_POR_TICKET = 3

    @staticmethod
    def ordenes_usados(cur, ticket_id):
        cur.execute(
            "SELECT orden FROM ticket_evidencias WHERE ticket_id = %s", (ticket_id,)
        )
        return {fila["orden"] for fila in cur.fetchall()}

    @staticmethod
    def insertar(cur, ticket_id, orden, info, subido_por):
        cur.execute(
            """INSERT INTO ticket_evidencias
                 (ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type, tamano_bytes, subido_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                ticket_id,
                orden,
                info["nombre_original"],
                info["nombre_archivo"],
                info["ruta"],
                info["mime_type"],
                info["tamano_bytes"],
                subido_por,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def listar_por_ticket(ticket_id):
        with conexion().cursor() as cur:
            cur.execute(
                """SELECT e.id, e.orden, e.nombre_original, e.ruta, e.mime_type, e.tamano_bytes,
                          e.created_at, e.subido_por AS subido_por_id, u.nombre AS subido_por
                     FROM ticket_evidencias e
                     JOIN users u ON u.id = e.subido_por
                    WHERE e.ticket_id = %s
                    ORDER BY e.orden""",
                (ticket_id,),
            )
            return cur.fetchall()

    @staticmethod
    def obtener(evidencia_id):
        with conexion().cursor() as cur:
            cur.execute(
                "SELECT * FROM ticket_evidencias WHERE id = %s", (evidencia_id,)
            )
            return cur.fetchone()

    @staticmethod
    def eliminar(cur, evidencia_id):
        cur.execute("DELETE FROM ticket_evidencias WHERE id = %s", (evidencia_id,))


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None

EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}
MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANO_MAXIMO = 5 * 1024 * 1024
LADO_MAXIMO = 1920
TAMANO_MINIATURA = (240, 240)
Image.MAX_IMAGE_PIXELS = 40_000_000

FORMATO_POR_MIME = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}


class ErrorEvidencia(ValueError):
    pass


def detectar_mime_real(cabecera: bytes):
    if cabecera[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if cabecera[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(archivo):
    nombre = archivo.filename or "archivo"
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorEvidencia(f"«{nombre}»: solo se permiten imágenes JPG, PNG o WEBP.")

    if (archivo.mimetype or "").lower() not in MIME_PERMITIDOS:
        raise ErrorEvidencia(
            f"«{nombre}»: el tipo de archivo no es una imagen permitida."
        )

    contenido = archivo.stream.read(TAMANO_MAXIMO + 1)
    if len(contenido) == 0:
        raise ErrorEvidencia(f"«{nombre}»: el archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ErrorEvidencia(f"«{nombre}»: supera el máximo de 5 MB.")

    mime_real = detectar_mime_real(contenido[:12])
    if mime_real is None:
        raise ErrorEvidencia(
            f"«{nombre}»: el contenido no es una imagen real (firma no válida)."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenido)) as img:
                img.verify()
                formato = img.format
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
    ):
        raise ErrorEvidencia(
            f"«{nombre}»: la imagen está dañada o es demasiado grande."
        )
    if FORMATO_POR_MIME[mime_real][0] != formato:
        raise ErrorEvidencia(
            f"«{nombre}»: el contenido no coincide con el tipo de imagen."
        )

    return {
        "nombre_original": nombre[-255:],
        "contenido": contenido,
        "mime_type": mime_real,
    }


def _a_rgb(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert("RGB")


def carpeta_proyecto():
    return current_app.root_path


def ruta_miniatura(ruta):
    return ruta.rsplit(".", 1)[0] + "_min.jpg"


def guardar_foto(foto, empresa_codigo, ticket_id):
    carpeta_relativa = f"uploads/{empresa_codigo}/{ticket_id}"
    carpeta = os.path.join(carpeta_proyecto(), *carpeta_relativa.split("/"))
    os.makedirs(carpeta, exist_ok=True)

    mime = foto["mime_type"]
    formato, extension = FORMATO_POR_MIME[mime]
    nombre_base = uuid.uuid4().hex

    with Image.open(io.BytesIO(foto["contenido"])) as original:
        img = ImageOps.exif_transpose(original)
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))

        destino = os.path.join(carpeta, f"{nombre_base}.{extension}")
        if formato == "JPEG":
            _a_rgb(img).save(destino, "JPEG", quality=85, optimize=True)
        elif formato == "PNG":
            img.save(destino, "PNG", optimize=True)
        else:
            img.save(destino, "WEBP", quality=85)

        if os.path.getsize(destino) > TAMANO_MAXIMO:
            os.remove(destino)
            mime, extension = "image/jpeg", "jpg"
            destino = os.path.join(carpeta, f"{nombre_base}.jpg")
            _a_rgb(img).save(destino, "JPEG", quality=80, optimize=True)

        miniatura = ImageOps.fit(
            _a_rgb(img), TAMANO_MINIATURA, Image.Resampling.LANCZOS
        )
        miniatura.save(
            os.path.join(carpeta, f"{nombre_base}_min.jpg"), "JPEG", quality=80
        )

    nombre_archivo = f"{nombre_base}.{extension}"
    return {
        "nombre_original": foto["nombre_original"],
        "nombre_archivo": nombre_archivo,
        "ruta": f"{carpeta_relativa}/{nombre_archivo}",
        "mime_type": mime,
        "tamano_bytes": os.path.getsize(destino),
    }


def borrar_archivos(rutas):
    for ruta in rutas:
        for archivo in (ruta, ruta_miniatura(ruta)):
            try:
                os.remove(os.path.join(carpeta_proyecto(), *archivo.split("/")))
            except FileNotFoundError:
                pass


def borrar_carpeta_ticket(empresa_codigo, ticket_id):
    shutil.rmtree(
        os.path.join(carpeta_proyecto(), "uploads", empresa_codigo, str(ticket_id)),
        ignore_errors=True,
    )

ROL_ADMIN = "Administrador"
ROL_TECNICO = "Técnico"
ROL_SOLICITANTE = "Solicitante"


def login_requerido(vista):

    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = g.get("usuario_token")
        if not usuario:
            return jsonify(
                error=g.get("error_token")
                or "Tu sesión expiró. Vuelve a iniciar sesión."
            ), 401
        usuario = dict(usuario)
        usuario["es_super"] = usuario["rol"] == ROL_SUPER
        if usuario["es_super"]:
            empresa_id = empresa_actual()
            if not empresa_id:
                return jsonify(
                    error="Elige primero la empresa que quieres administrar (menú Empresas)."
                ), 403
            with conexion().cursor() as cur:
                cur.execute(
                    "SELECT id, codigo, nombre FROM empresas WHERE id = %s",
                    (empresa_id,),
                )
                empresa = cur.fetchone()
            if not empresa:
                return jsonify(error="La empresa elegida ya no existe."), 404
            usuario.update(
                empresa_id=empresa["id"],
                empresa=empresa["nombre"],
                empresa_codigo=empresa["codigo"],
                rol=ROL_ADMIN,
            )
        g.usuario = usuario
        return vista(*args, **kwargs)

    return envoltura


def puede_ver(usuario, ticket):
    if usuario["rol"] in (ROL_SUPER, ROL_ADMIN):
        return True
    if usuario["rol"] == ROL_SOLICITANTE:
        return ticket["solicitante_id"] == usuario["id"]
    if usuario["rol"] == ROL_TECNICO:
        return ticket["tecnico_id"] is None or ticket["tecnico_id"] == usuario["id"]
    return False

def _ticket_o_error(ticket_id):
    ticket = Ticket.obtener(ticket_id, g.usuario["empresa_id"])
    if ticket is None or not puede_ver(g.usuario, ticket):
        return None, (
            jsonify(error="Usted no tiene acceso a este ticket o no existe en esta empresa."),
            403,
        )
    return ticket, None


def puede_editar(usuario, ticket):
    if ticket["estado"] == "Cerrado":
        return False
    if usuario["rol"] == ROL_ADMIN:
        return True
    if usuario["rol"] == ROL_SOLICITANTE:
        return (
            ticket["solicitante_id"] == usuario["id"] and ticket["estado"] == "Abierto"
        )
    return False


def puede_adjuntar(usuario, ticket):
    if ticket["estado"] == "Cerrado":
        return False
    return (
        usuario["rol"] in (ROL_ADMIN, ROL_TECNICO)
        or ticket["solicitante_id"] == usuario["id"]
    )


def puede_eliminar(usuario, ticket):
    if usuario["rol"] == ROL_ADMIN:
        return True
    return (
        ticket["solicitante_id"] == usuario["id"]
        and ticket["estado"] == "Abierto"
        and ticket["tecnico_id"] is None
    )

@tickets_bp.record_once
def _configurar(state):
    app = state.app
    if not app.config.get("MAX_CONTENT_LENGTH"):
        app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@tickets_bp.app_errorhandler(RequestEntityTooLarge)
def _demasiado_grande(error):
    if request.path.startswith("/api/"):
        return jsonify(
            error="Los archivos superan el tamaño total permitido (16 MB)."
        ), 413
    return error


@tickets_bp.errorhandler(ErrorRegla)
def _error_regla(error):
    return jsonify(error=str(error)), 400


@tickets_bp.errorhandler(pymysql.MySQLError)
def _error_mysql(error):
    if error.args and error.args[0] == 1644:
        return jsonify(error=error.args[1]), 400
    current_app.logger.exception("Error de base de datos en tickets")
    return jsonify(error="Error de base de datos. Inténtalo nuevamente."), 500


def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor else None


def _urls_evidencia(evidencia_id):
    return {
        "miniatura_url": url_for(
            "tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="miniatura"
        ),
        "imagen_url": url_for(
            "tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="imagen"
        ),
    }


def _ticket_base(t):
    return {
        "id": t["id"],
        "codigo": t["codigo"],
        "asunto": t["asunto"],
        "empresa": t["empresa"],
        "categoria_id": t["categoria_id"],
        "categoria": t["categoria"],
        "area_id": t["area_id"],
        "area": t["area"],
        "prioridad_id": t["prioridad_id"],
        "prioridad": t["prioridad"],
        "sla_horas": t["sla_horas"],
        "estado": t["estado"],
        "solicitante_id": t["solicitante_id"],
        "solicitante": t["solicitante"],
        "tecnico_id": t["tecnico_id"],
        "tecnico": t["tecnico"] if t["tecnico_id"] else None,
        "created_at": _fecha(t["created_at"]),
        "fecha_limite": _fecha(t["fecha_limite"]),
        "semaforo": t["semaforo"],
        "minutos_restantes": t["minutos_restantes"],
        "minutos_transcurridos": t.get("minutos_transcurridos"),
        "porcentaje_sla": t.get("porcentaje_sla"),
        "sla_texto": t.get("sla_texto"),
        "total_evidencias": t["total_evidencias"],
    }


def _ticket_resumen(t):
    datos = _ticket_base(t)
    datos.update(miniatura_url=None, imagen_url=None)
    if t["primera_evidencia_id"]:
        datos.update(_urls_evidencia(t["primera_evidencia_id"]))
    return datos


def _ticket_detalle(t, usuario):
    datos = _ticket_base(t)
    datos["descripcion"] = t["descripcion"]
    datos["evidencias"] = [
        {
            "id": e["id"],
            "orden": e["orden"],
            "nombre": e["nombre_original"],
            "mime_type": e["mime_type"],
            "tamano_bytes": e["tamano_bytes"],
            "subido_por": e["subido_por"],
            "subido_por_id": e["subido_por_id"],
            "created_at": _fecha(e["created_at"]),
            **_urls_evidencia(e["id"]),
        }
        for e in Evidencia.listar_por_ticket(t["id"])
    ]
    datos["max_evidencias"] = Evidencia.MAX_POR_TICKET
    datos["permisos"] = {
        "editar": puede_editar(usuario, t),
        "adjuntar": puede_adjuntar(usuario, t),
        "eliminar": puede_eliminar(usuario, t),
    }
    return datos


def _fotos_de_la_peticion():
    return [a for a in request.files.getlist("fotos") if a and a.filename]


def _guardar_fotos(cur, ticket_id, fotos, guardadas):
    libres = [
        n
        for n in range(1, Evidencia.MAX_POR_TICKET + 1)
        if n not in Evidencia.ordenes_usados(cur, ticket_id)
    ]
    for foto, orden in zip(fotos, libres):
        info = guardar_foto(foto, g.usuario["empresa_codigo"], ticket_id)
        guardadas.append(info["ruta"])
        Evidencia.insertar(cur, ticket_id, orden, info, g.usuario["id"])


@tickets_bp.get("/api/tickets/sesion")
@login_requerido
def sesion_actual():
    u = g.usuario
    return jsonify(
        usuario={
            "id": u["id"],
            "nombre": u["nombre"],
            "correo": u["correo"],
            "rol": u["rol"],
            "empresa": u["empresa"],
            "area_id": u["area_id"],
            "area": u["area"],
        },
        catalogos={
            "categorias": Catalogo.categorias(),
            "prioridades": Catalogo.prioridades(),
            "areas": Catalogo.areas(u["empresa_id"]),
            "max_evidencias": Evidencia.MAX_POR_TICKET,
            "max_mb_por_foto": TAMANO_MAXIMO // (1024 * 1024),
        },
    )


@tickets_bp.post("/api/tickets")
@login_requerido
def crear_ticket():
    if g.usuario["es_super"]:
        return jsonify(
            error="El superusuario no registra tickets: inicia sesión con un usuario de la empresa."
        ), 403
    datos, errores = Ticket.validar(request.form, g.usuario)
    archivos = _fotos_de_la_peticion()
    if len(archivos) > Evidencia.MAX_POR_TICKET:
        errores["fotos"] = (
            f"Puedes adjuntar como máximo {Evidencia.MAX_POR_TICKET} fotos."
        )
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400

    try:
        fotos = [validar_foto(a) for a in archivos]
    except ErrorEvidencia as e:
        return jsonify(error=str(e), errores={"fotos": str(e)}), 415

    con = conexion()
    ticket_id = None

    try:
        with con.cursor() as cur:
            ticket_id = Ticket.crear(
                cur, datos, g.usuario["id"], g.usuario["empresa_id"]
            )
            if (request.form.get("equipo") or "").strip():
                from equipos import vincular_equipo

                vincular_equipo(
                    cur, ticket_id, request.form["equipo"], g.usuario["empresa_id"]
                )
            _guardar_fotos(cur, ticket_id, fotos, [])
        con.commit()
    except Exception:
        con.rollback()
        if ticket_id:
            borrar_carpeta_ticket(g.usuario["empresa_codigo"], ticket_id)
        raise

    ticket = _ticket_detalle(
        Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario
    )
    return (
        jsonify(mensaje=f"Ticket {ticket['codigo']} registrado.", ticket=ticket),
        201,
        {"Location": url_for("tickets.obtener_ticket", ticket_id=ticket_id)},
    )


@tickets_bp.get("/api/tickets")
@login_requerido
def listar_tickets():
    limite = _entero(request.args.get("limite")) or 100
    filtros = {
        "estado": request.args.get("estado"),
        "prioridad": request.args.get("prioridad"),
        "q": (request.args.get("q") or "").strip()[:60],
        "mios": request.args.get("mios") == "1",
        "limite": max(1, min(limite, 500)),
    }

    tickets = [_ticket_resumen(t) for t in Ticket.listar(g.usuario, filtros)]
    return jsonify(tickets=tickets, total=len(tickets))


@tickets_bp.get("/api/tickets/<int:ticket_id>")
@login_requerido
def obtener_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    return jsonify(ticket=_ticket_detalle(ticket, g.usuario))


@tickets_bp.put("/api/tickets/<int:ticket_id>")
@login_requerido
def editar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error

    datos = request.get_json(silent=True) or request.form
    con = conexion()
    cambios = None

    try:
        with con.cursor() as cur:
            if (
                any(k in datos for k in ("estado", "tecnico", "prioridad", "categoria"))
                and "asunto" not in datos
            ):
                if (
                    g.usuario["rol"] == ROL_SOLICITANTE
                    and ticket["estado"] == "Cerrado"
                ):
                    return jsonify(error="No puedes modificar un ticket cerrado."), 403
                cambios = Ticket.actualizar_gestion(cur, ticket_id, datos, g.usuario)

            elif "asunto" in datos:
                if not puede_editar(g.usuario, ticket):
                    return jsonify(
                        error="Solo puedes editar tus tickets mientras estén «Abierto»."
                    ), 403

                limpios, errores = Ticket.validar(datos, g.usuario)
                if errores:
                    return jsonify(
                        error="Revisa los campos marcados.", errores=errores
                    ), 400

                Ticket.actualizar(cur, ticket_id, limpios, g.usuario["empresa_id"])

        con.commit()
    except ErrorRegla as e:
        con.rollback()
        return jsonify(error=str(e)), 400
    except Exception:
        con.rollback()
        raise

    aviso = None
    if cambios and cambios.get("tecnico_avisar"):
        from avisos_whatsapp import avisar_asignacion

        aviso = avisar_asignacion(
            ticket_id,
            cambios["tecnico_avisar"],
            cambios["reasignacion"],
            g.usuario["empresa_id"],
            g.usuario["id"],
        )

    return jsonify(
        mensaje="Ticket actualizado correctamente.",
        ticket=_ticket_detalle(
            Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario
        ),
        aviso_whatsapp=aviso,
    )


@tickets_bp.delete("/api/tickets/<int:ticket_id>")
@login_requerido
def eliminar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not puede_eliminar(g.usuario, ticket):
        return jsonify(
            error="Este ticket ya está en atención y no se puede eliminar."
        ), 403

    con = conexion()
    with con.cursor() as cur:
        Ticket.eliminar(cur, ticket_id)
    con.commit()
    borrar_carpeta_ticket(g.usuario["empresa_codigo"], ticket_id)
    return jsonify(mensaje=f"Ticket {ticket['codigo']} eliminado.")


@tickets_bp.post("/api/tickets/<int:ticket_id>/evidencias")
@login_requerido
def agregar_evidencias(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not puede_adjuntar(g.usuario, ticket):
        return jsonify(error="No puedes adjuntar fotos a este ticket."), 403

    archivos = _fotos_de_la_peticion()
    if not archivos:
        msg = "Selecciona al menos una foto."
        return jsonify(error=msg, errores={"fotos": msg}), 400
    try:
        fotos = [validar_foto(a) for a in archivos]
    except ErrorEvidencia as e:
        return jsonify(error=str(e), errores={"fotos": str(e)}), 415

    con = conexion()
    guardadas = []
    try:
        with con.cursor() as cur:
            Ticket.bloquear(cur, ticket_id)
            actuales = len(Evidencia.ordenes_usados(cur, ticket_id))
            disponibles = Evidencia.MAX_POR_TICKET - actuales
            if len(fotos) > disponibles:
                con.rollback()
                msg = (
                    f"El ticket ya tiene {actuales} foto(s). "
                    f"Solo puedes agregar {max(disponibles, 0)} más."
                )
                return jsonify(error=msg, errores={"fotos": msg}), 409
            _guardar_fotos(cur, ticket_id, fotos, guardadas)
        con.commit()
    except Exception:
        con.rollback()
        borrar_archivos(guardadas)
        raise
    return jsonify(
        mensaje=f"{len(fotos)} foto(s) agregada(s).",
        ticket=_ticket_detalle(
            Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario
        ),
    ), 201


@tickets_bp.delete("/api/tickets/<int:ticket_id>/evidencias/<int:evidencia_id>")
@login_requerido
def eliminar_evidencia(ticket_id, evidencia_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    evidencia = Evidencia.obtener(evidencia_id)
    if evidencia is None or evidencia["ticket_id"] != ticket_id:
        return jsonify(error="La foto no existe."), 404
    if not (
        puede_editar(g.usuario, ticket)
        or (
            evidencia["subido_por"] == g.usuario["id"] and ticket["estado"] != "Cerrado"
        )
    ):
        return jsonify(error="No puedes quitar esta foto."), 403

    con = conexion()
    with con.cursor() as cur:
        Evidencia.eliminar(cur, evidencia_id)
    con.commit()
    borrar_archivos([evidencia["ruta"]])
    return jsonify(
        mensaje="Foto eliminada.",
        ticket=_ticket_detalle(
            Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario
        ),
    )


@tickets_bp.get("/api/tickets/<int:ticket_id>/historial")
@login_requerido
def obtener_historial_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error

    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            f"""SELECT id, tipo, estado_anterior, estado_nuevo, tecnico_anterior,
                      tecnico_nuevo, comentario, usuario, usuario_rol, created_at, minutos_desde
                 FROM {V_TICKET_TIMELINE} AS h
                WHERE h.ticket_id = %s
                ORDER BY created_at ASC""",
            (ticket_id,),
        )
        historial = cur.fetchall()

        for item in historial:
            item["created_at"] = _fecha(item["created_at"])

    return jsonify(historial=historial)


@tickets_bp.post("/api/tickets/<int:ticket_id>/comentarios")
@login_requerido
def comentar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    datos = request.get_json(silent=True) or request.form
    comentario = (datos.get("comentario") or "").strip()
    if len(comentario) < 2:
        return jsonify(error="Escribe un comentario."), 400
    if len(comentario) > Ticket.MAX_COMENTARIO:
        return jsonify(
            error=f"El comentario no puede superar los {Ticket.MAX_COMENTARIO} caracteres."
        ), 400
    if ticket["estado"] == "Cerrado":
        return jsonify(error="El ticket está cerrado y ya no admite comentarios."), 400
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute(
                """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                   VALUES (%s, %s, 'COMENTARIO', %s, NOW())""",
                (ticket_id, g.usuario["id"], comentario),
            )
            destinatarios = {ticket["solicitante_id"], ticket["tecnico_id"]}
            if not ticket["tecnico_id"]:
                cur.execute(
                    "SELECT id FROM users WHERE empresa_id = %s AND rol = %s AND activo = 1",
                    (ticket["empresa_id"], ROL_ADMIN),
                )
                destinatarios |= {f["id"] for f in cur.fetchall()}

            destinos_finales = destinatarios - {None, g.usuario["id"]}

            for destino in destinos_finales:
                cur.execute(
                    """INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje)
                       VALUES (%s, 'COMENTARIO', %s, %s, %s)""",
                    (
                        destino,
                        ticket_id,
                        f"Nuevo comentario en {ticket['codigo']}",
                        f"{g.usuario['nombre']}: {comentario}"[:255],
                    ),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise

    try:
        emitir_comentario_ticket(
            ticket_id,
            {
                "ticket_id": ticket_id,
                "tipo": "COMENTARIO",
                "usuario": g.usuario["nombre"],
                "usuario_rol": g.usuario["rol"],
                "comentario": comentario,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
            destinatarios_ids=list(destinos_finales),
        )
    except Exception as e:
        current_app.logger.warning(f"Error al emitir comentario SSE: {e}")

    return jsonify(mensaje="Comentario agregado."), 201


def _puede_gestionar_tareas(usuario, ticket):
    return ticket["estado"] != "Cerrado" and (
        usuario["rol"] == ROL_ADMIN
        or (usuario["rol"] == ROL_TECNICO and ticket["tecnico_id"] == usuario["id"])
    )


def _tareas_json(ticket_id):
    with conexion().cursor() as cur:
        cur.execute(
            """SELECT ta.id, ta.descripcion, ta.completada, ta.created_at, ta.completada_at,
                      c.nombre AS creado_por, cp.nombre AS completada_por
                 FROM ticket_tareas ta
                 JOIN users c ON c.id = ta.creado_por
                 LEFT JOIN users cp ON cp.id = ta.completada_por
                WHERE ta.ticket_id = %s
                ORDER BY ta.completada, ta.id""",
            (ticket_id,),
        )
        filas = cur.fetchall()
    for f in filas:
        f["completada"] = bool(f["completada"])
        f["created_at"] = _fecha(f["created_at"])
        f["completada_at"] = _fecha(f["completada_at"])
    return filas


def _tarea_y_ticket(tarea_id):
    with conexion().cursor() as cur:
        cur.execute(
            "SELECT id, ticket_id, descripcion, completada FROM ticket_tareas WHERE id = %s",
            (tarea_id,),
        )
        tarea = cur.fetchone()
    if not tarea:
        return None, None, (jsonify(error="La tarea no existe."), 404)
    ticket, error = _ticket_o_error(tarea["ticket_id"])
    if error:
        return None, None, error
    if not _puede_gestionar_tareas(g.usuario, ticket):
        return (
            None,
            None,
            (
                jsonify(
                    error="Solo el administrador o el técnico asignado pueden modificar las tareas."
                ),
                403,
            ),
        )
    return tarea, ticket, None


@tickets_bp.get("/api/tickets/<int:ticket_id>/tareas")
@login_requerido
def listar_tareas(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    return jsonify(
        tareas=_tareas_json(ticket_id),
        puede_editar=_puede_gestionar_tareas(g.usuario, ticket),
    )


@tickets_bp.post("/api/tickets/<int:ticket_id>/tareas")
@login_requerido
def crear_tarea(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not _puede_gestionar_tareas(g.usuario, ticket):
        return jsonify(
            error="Solo el administrador o el técnico asignado pueden agregar tareas."
        ), 403
    datos = request.get_json(silent=True) or request.form
    descripcion = " ".join((datos.get("descripcion") or "").split())
    if not 3 <= len(descripcion) <= 200:
        return jsonify(error="La tarea debe tener entre 3 y 200 caracteres."), 400
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO ticket_tareas (ticket_id, descripcion, creado_por, created_at) VALUES (%s, %s, %s, NOW())",
            (ticket_id, descripcion, g.usuario["id"]),
        )
    con.commit()
    return jsonify(mensaje="Tarea agregada.", tareas=_tareas_json(ticket_id)), 201


@tickets_bp.put("/api/tareas/<int:tarea_id>")
@login_requerido
def marcar_tarea(tarea_id):
    tarea, ticket, error = _tarea_y_ticket(tarea_id)
    if error:
        return error
    datos = request.get_json(silent=True) or {}
    completada = bool(datos.get("completada"))
    con = conexion()
    try:
        with con.cursor() as cur:
            cur.execute(
                """UPDATE ticket_tareas
                      SET completada = %s, completada_por = %s, completada_at = IF(%s, NOW(), NULL)
                    WHERE id = %s""",
                (
                    int(completada),
                    g.usuario["id"] if completada else None,
                    int(completada),
                    tarea_id,
                ),
            )
            if completada and not tarea["completada"]:
                cur.execute(
                    """INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, comentario, created_at)
                       VALUES (%s, %s, 'COMENTARIO', %s, NOW())""",
                    (
                        ticket["id"],
                        g.usuario["id"],
                        f"Tarea completada: {tarea['descripcion']}",
                    ),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return jsonify(mensaje="Tarea actualizada.", tareas=_tareas_json(ticket["id"]))


@tickets_bp.delete("/api/tareas/<int:tarea_id>")
@login_requerido
def borrar_tarea(tarea_id):
    tarea, ticket, error = _tarea_y_ticket(tarea_id)
    if error:
        return error
    con = conexion()
    with con.cursor() as cur:
        cur.execute("DELETE FROM ticket_tareas WHERE id = %s", (tarea_id,))
    con.commit()
    return jsonify(mensaje="Tarea eliminada.", tareas=_tareas_json(ticket["id"]))


@tickets_bp.get("/api/tecnicos")
@login_requerido
def listar_tecnicos():
    if g.usuario["rol"] == ROL_SOLICITANTE:
        return jsonify(error="No tienes acceso a esta información."), 403
    with conexion().cursor() as cur:
        cur.execute(
            """SELECT u.id, u.nombre, (u.telefono IS NOT NULL) AS tiene_whatsapp,
                      (SELECT COUNT(*) FROM tickets t
                        WHERE t.tecnico_id = u.id AND t.estado IN ('Abierto', 'En proceso')) AS activos
                 FROM users u
                WHERE u.empresa_id = %s AND u.rol = %s AND u.activo = 1
                ORDER BY u.nombre""",
            (g.usuario["empresa_id"], ROL_TECNICO),
        )
        tecnicos = cur.fetchall()
    return jsonify(tecnicos=tecnicos)


@tickets_bp.get("/api/historial/reciente")
@login_requerido
def historial_reciente():
    if g.usuario["rol"] == ROL_SOLICITANTE:
        return jsonify(error="No tienes acceso a esta información."), 403
    try:
        limite = max(1, min(int(request.args.get("limite", 50)), 300))
    except ValueError:
        limite = 50
    with conexion().cursor() as cur:
        cur.execute(
            f"""SELECT h.id, h.ticket_id, v.codigo, h.tipo, h.estado_anterior, h.estado_nuevo,
                      h.tecnico_anterior, h.tecnico_nuevo, h.comentario, h.usuario,
                      h.usuario_rol, h.created_at, h.minutos_desde
                 FROM {V_TICKET_TIMELINE} h
                 JOIN {V_TICKETS} v ON v.id = h.ticket_id
                WHERE h.empresa_id = %s
                ORDER BY h.created_at DESC, h.id DESC
                LIMIT %s""",
            (g.usuario["empresa_id"], limite),
        )
        historial = cur.fetchall()
        cur.execute(
            f"""SELECT COUNT(*) AS total FROM {V_TICKET_TIMELINE} AS h
                WHERE h.empresa_id = %s AND tipo <> 'CREACION' AND DATE(created_at) = CURDATE()""",
            (g.usuario["empresa_id"],),
        )
        movimientos_hoy = cur.fetchone()["total"]
    for item in historial:
        item["created_at"] = _fecha(item["created_at"])
    return jsonify(historial=historial, movimientos_hoy=movimientos_hoy)


@tickets_bp.get("/api/evidencias/<int:evidencia_id>/<any(miniatura, imagen):tipo>")
@login_requerido
def ver_evidencia(evidencia_id, tipo):
    evidencia = Evidencia.obtener(evidencia_id)
    ticket = evidencia and Ticket.obtener(
        evidencia["ticket_id"], g.usuario["empresa_id"]
    )
    if not ticket:
        return jsonify(error="La foto no existe."), 404
    if not puede_ver(g.usuario, ticket):
        return jsonify(error="No tienes acceso a esta foto."), 403
    if tipo == "miniatura":
        ruta, mime = ruta_miniatura(evidencia["ruta"]), "image/jpeg"
    else:
        ruta, mime = evidencia["ruta"], evidencia["mime_type"]
    respuesta = send_from_directory(carpeta_proyecto(), ruta, mimetype=mime, max_age=0)
    respuesta.headers["Cache-Control"] = "private, max-age=600"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


# ==========================================
# RUTAS PARA TICKET_HISTORIAL
# ==========================================

# @tickets_bp.route('/api_insertar_historial', methods=['POST'])
""" def api_insertar_historial():
    rpta = dict()
    try:
        objConexion = obtener_conexion()
        # Ajusta los nombres de estos campos según el JSON que envíes desde Postman
        v_ticket_id = request.json["ticket_id"]
        v_accion = request.json["accion"]
        v_detalles = request.json.get("detalles", "") # .get() evita error si viene vacío

        with objConexion:
            with objConexion.cursor() as cursor:
                sql = "INSERT INTO `ticket_historial` (`ticket_id`, `accion`, `detalles`) VALUES (%s, %s, %s)"
                cursor.execute(sql, (v_ticket_id, v_accion, v_detalles))
            objConexion.commit()

        rpta["status"] = 1
        rpta["data"] = {}
        rpta["message"] = "Historial del ticket registrado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    return jsonify(rpta)

# @tickets_bp.route('/api_obtener_historial', methods=['GET'])
def api_obtener_historial():
    rpta = dict()
    try:
        # Permite filtrar por ticket si envías ?ticket_id=X en la URL
        v_ticket_id = request.args.get('ticket_id')

        objConexion = obtener_conexion()
        with objConexion:
            with objConexion.cursor() as cursor:
                if v_ticket_id:
                    sql = "SELECT * FROM `ticket_historial` WHERE `ticket_id` = %s"
                    cursor.execute(sql, (v_ticket_id,))
                else:
                    sql = "SELECT * FROM `ticket_historial`"
                    cursor.execute(sql)
                result = cursor.fetchall()

        rpta["status"] = 1
        rpta["data"] = result
        rpta["message"] = "Historial listado correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    return jsonify(rpta)


# ==========================================
# RUTAS PARA NOTIFICACIONES
# ==========================================

# @tickets_bp.route('/api_insertar_notificacion', methods=['POST'])
def api_insertar_notificacion():
    rpta = dict()
    try:
        objConexion = obtener_conexion()
        v_usuario_id = request.json["usuario_id"]
        v_mensaje = request.json["mensaje"]
        v_estado = request.json.get("estado", "Pendiente")

        with objConexion:
            with objConexion.cursor() as cursor:
                sql = "INSERT INTO `notificaciones` (`usuario_id`, `mensaje`, `estado`) VALUES (%s, %s, %s)"
                cursor.execute(sql, (v_usuario_id, v_mensaje, v_estado))
            objConexion.commit()

        rpta["status"] = 1
        rpta["data"] = {}
        rpta["message"] = "Notificación generada correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    return jsonify(rpta)

# @tickets_bp.route('/api_obtener_notificaciones', methods=['GET'])
def api_obtener_notificaciones():
    rpta = dict()
    try:
        objConexion = obtener_conexion()
        with objConexion:
            with objConexion.cursor() as cursor:
                sql = "SELECT * FROM `notificaciones` ORDER BY id DESC"
                cursor.execute(sql)
                result = cursor.fetchall()

        rpta["status"] = 1
        rpta["data"] = result
        rpta["message"] = "Notificaciones listadas correctamente"
    except Exception as e:
        rpta["status"] = -1
        rpta["data"] = {}
        rpta["message"] = "Error: " + repr(e)
    return jsonify(rpta) """
