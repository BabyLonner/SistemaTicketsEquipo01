"""
Tickets — registro de tickets con evidencias fotográficas (Flask + MySQL).

Trabaja sobre la base mesa_ayuda_ti (database/mesa_ayuda_ti.sql):
    tickets, ticket_evidencias, categorias, prioridades, areas y la vista v_tickets.
Los triggers de la base ponen la empresa, el correlativo (EPS-0001...), la
fecha límite del SLA y el primer registro del historial.

Contenido (patrón MVC):
    1. Conexión a MySQL (usa db.py del proyecto)
    2. Modelo: clases Catalogo, Ticket y Evidencia
    3. Fotos de evidencia: validación MIME, guardado en /uploads y miniaturas
    4. Seguridad: usuario de la sesión (login de run.py) y permisos por rol
    5. Controlador: API JSON

Se registra en run.py con:  app.register_blueprint(tickets_bp)
"""
import io
import os
import shutil
import uuid
import warnings
from functools import wraps

import pymysql
from flask import (Blueprint, current_app, g, jsonify, request,
                   send_from_directory, session, url_for)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

from db import obtener_conexion as nueva_conexion

tickets_bp = Blueprint("tickets", __name__)


# =====================================================================
# 1. CONEXIÓN A MYSQL
# =====================================================================
def conexion():
    """Una conexión por petición HTTP (se cierra sola al terminar)."""
    if "db_tickets" not in g:
        g.db_tickets = nueva_conexion()
    return g.db_tickets


@tickets_bp.teardown_app_request
def _cerrar_conexion(_error=None):
    con = g.pop("db_tickets", None)
    if con is not None:
        con.close()


# =====================================================================
# 2. MODELO: Catalogo, Ticket, Evidencia
# =====================================================================
class Catalogo:
    """Listas para el formulario (categorías, prioridades y áreas de la empresa)."""

    @staticmethod
    def categorias():
        with conexion().cursor() as cur:
            cur.execute("SELECT id, nombre FROM categorias WHERE activo = 1 ORDER BY nombre")
            return cur.fetchall()

    @staticmethod
    def prioridades():
        with conexion().cursor() as cur:
            cur.execute("SELECT id, nombre, sla_horas FROM prioridades ORDER BY nivel DESC")
            return cur.fetchall()

    @staticmethod
    def areas(empresa_id):
        with conexion().cursor() as cur:
            cur.execute("SELECT id, nombre FROM areas WHERE empresa_id = %s AND activo = 1 ORDER BY nombre",
                        (empresa_id,))
            return cur.fetchall()


class Ticket:
    ESTADOS = ("Abierto", "En proceso", "Resuelto", "Cerrado")

    @staticmethod
    def validar(datos, usuario):
        """Limpia y valida el formulario. Devuelve (limpios, errores).

        El solicitante y la empresa NO vienen del formulario: salen de la sesión.
        """
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

        # La prioridad puede llegar como nombre ("Alta") o como id
        prioridades = Catalogo.prioridades()
        valor = str(datos.get("prioridad") or datos.get("prioridad_id") or "").strip()
        prioridad_id = next((p["id"] for p in prioridades
                             if valor in (p["nombre"], str(p["id"]))), None)
        if prioridad_id is None:
            errores["prioridad"] = "La prioridad debe ser Alta, Media o Baja."

        # Área: debe ser de la empresa del usuario; si no se envía, se usa la del usuario
        area_id = _entero(datos.get("area_id")) or usuario["area_id"]
        if area_id is not None and area_id not in {a["id"] for a in Catalogo.areas(usuario["empresa_id"])}:
            errores["area_id"] = "Selecciona un área válida."

        limpios = {"asunto": asunto, "descripcion": descripcion, "categoria_id": categoria_id,
                   "prioridad_id": prioridad_id, "area_id": area_id}
        return limpios, errores

    @staticmethod
    def crear(cur, datos, solicitante_id):
        cur.execute(
            """INSERT INTO tickets (solicitante_id, area_id, categoria_id, prioridad_id, asunto, descripcion)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (solicitante_id, datos["area_id"], datos["categoria_id"], datos["prioridad_id"],
             datos["asunto"], datos["descripcion"]),
        )
        return cur.lastrowid

    @staticmethod
    def actualizar(cur, ticket_id, datos):
        cur.execute(
            """UPDATE tickets
                  SET asunto = %s, descripcion = %s, categoria_id = %s, prioridad_id = %s, area_id = %s
                WHERE id = %s""",
            (datos["asunto"], datos["descripcion"], datos["categoria_id"], datos["prioridad_id"],
             datos["area_id"], ticket_id),
        )

    @staticmethod
    def eliminar(cur, ticket_id):
        # evidencias, historial y notificaciones se borran en cascada
        cur.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))

    @staticmethod
    def bloquear(cur, ticket_id):
        """SELECT ... FOR UPDATE: evita que dos subidas simultáneas pasen de 3 fotos."""
        cur.execute("SELECT id FROM tickets WHERE id = %s FOR UPDATE", (ticket_id,))
        return cur.fetchone() is not None

    @staticmethod
    def obtener(ticket_id, empresa_id):
        """Siempre filtrado por la empresa del usuario en sesión."""
        with conexion().cursor() as cur:
            cur.execute("SELECT * FROM v_tickets WHERE id = %s AND empresa_id = %s",
                        (ticket_id, empresa_id))
            return cur.fetchone()

    @staticmethod
    def listar(usuario, filtros):
        condiciones, params = ["v.empresa_id = %s"], [usuario["empresa_id"]]

        # Solicitante: sus tickets. Técnico: los asignados a él. Administrador: todos.
        if usuario["rol"] == "Solicitante" or filtros.get("mios"):
            condiciones.append("v.solicitante_id = %s")
            params.append(usuario["id"])
        elif usuario["rol"] == "Técnico":
            condiciones.append("v.tecnico_id = %s")
            params.append(usuario["id"])
        if filtros.get("estado") in Ticket.ESTADOS:
            condiciones.append("v.estado = %s")
            params.append(filtros["estado"])
        if filtros.get("prioridad"):
            condiciones.append("v.prioridad = %s")
            params.append(filtros["prioridad"])
        if filtros.get("q"):
            condiciones.append("(v.asunto LIKE %s OR v.codigo LIKE %s)")
            params += [f"%{filtros['q']}%"] * 2
        params.append(filtros.get("limite", 100))

        with conexion().cursor() as cur:
            cur.execute(
                f"""SELECT v.*,
                           (SELECT e.id FROM ticket_evidencias e
                             WHERE e.ticket_id = v.id ORDER BY e.orden LIMIT 1) AS primera_evidencia_id
                      FROM v_tickets v
                     WHERE {" AND ".join(condiciones)}
                     ORDER BY v.created_at DESC, v.id DESC
                     LIMIT %s""",
                params,
            )
            return cur.fetchall()


class Evidencia:
    MAX_POR_TICKET = 3

    @staticmethod
    def ordenes_usados(cur, ticket_id):
        cur.execute("SELECT orden FROM ticket_evidencias WHERE ticket_id = %s", (ticket_id,))
        return {fila["orden"] for fila in cur.fetchall()}

    @staticmethod
    def insertar(cur, ticket_id, orden, info, subido_por):
        cur.execute(
            """INSERT INTO ticket_evidencias
                 (ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type, tamano_bytes, subido_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (ticket_id, orden, info["nombre_original"], info["nombre_archivo"], info["ruta"],
             info["mime_type"], info["tamano_bytes"], subido_por),
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
            cur.execute("SELECT * FROM ticket_evidencias WHERE id = %s", (evidencia_id,))
            return cur.fetchone()

    @staticmethod
    def eliminar(cur, evidencia_id):
        cur.execute("DELETE FROM ticket_evidencias WHERE id = %s", (evidencia_id,))


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


# =====================================================================
# 3. FOTOS DE EVIDENCIA
# =====================================================================
# Validación en 4 capas: extensión, MIME declarado, MIME REAL por firma
# binaria (magic numbers) y decodificación con Pillow. Las imágenes se
# re-guardan con Pillow (sin metadatos EXIF) en:
#     uploads/<empresa>/<ticket_id>/<uuid>.jpg      imagen completa
#     uploads/<empresa>/<ticket_id>/<uuid>_min.jpg  miniatura del listado
EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}
MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANO_MAXIMO = 5 * 1024 * 1024        # 5 MB por foto (igual que el CHECK de la tabla)
LADO_MAXIMO = 1920                     # px de la imagen completa guardada
TAMANO_MINIATURA = (240, 240)          # px de la miniatura del listado
Image.MAX_IMAGE_PIXELS = 40_000_000    # protege contra "bombas" de descompresión

FORMATO_POR_MIME = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}


class ErrorEvidencia(ValueError):
    """Error de validación de una foto (se muestra tal cual al usuario)."""


def detectar_mime_real(cabecera: bytes):
    """Tipo MIME según los primeros bytes del archivo, o None.

        JPEG: FF D8 FF      PNG: 89 50 4E 47 0D 0A 1A 0A      WEBP: 'RIFF' ... 'WEBP'
    """
    if cabecera[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if cabecera[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(archivo):
    """Valida un archivo de request.files. Devuelve bytes + MIME real o lanza ErrorEvidencia."""
    nombre = archivo.filename or "archivo"

    # 1) Extensión
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorEvidencia(f"«{nombre}»: solo se permiten imágenes JPG, PNG o WEBP.")

    # 2) MIME declarado por el navegador
    if (archivo.mimetype or "").lower() not in MIME_PERMITIDOS:
        raise ErrorEvidencia(f"«{nombre}»: el tipo de archivo no es una imagen permitida.")

    contenido = archivo.stream.read(TAMANO_MAXIMO + 1)
    if len(contenido) == 0:
        raise ErrorEvidencia(f"«{nombre}»: el archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ErrorEvidencia(f"«{nombre}»: supera el máximo de 5 MB.")

    # 3) MIME real por firma binaria
    mime_real = detectar_mime_real(contenido[:12])
    if mime_real is None:
        raise ErrorEvidencia(f"«{nombre}»: el contenido no es una imagen real (firma no válida).")

    # 4) Pillow debe poder abrirla y su formato debe coincidir con la firma
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(contenido)) as img:
                img.verify()
                formato = img.format
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, SyntaxError):
        raise ErrorEvidencia(f"«{nombre}»: la imagen está dañada o es demasiado grande.")
    if FORMATO_POR_MIME[mime_real][0] != formato:
        raise ErrorEvidencia(f"«{nombre}»: el contenido no coincide con el tipo de imagen.")

    return {"nombre_original": nombre[-255:], "contenido": contenido, "mime_type": mime_real}


def _a_rgb(img):
    """Convierte a RGB; si la imagen tiene transparencia la pone sobre blanco."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert("RGB")


def carpeta_proyecto():
    return current_app.root_path


def ruta_miniatura(ruta):
    """uploads/epsel/12/abc.png -> uploads/epsel/12/abc_min.jpg"""
    return ruta.rsplit(".", 1)[0] + "_min.jpg"


def guardar_foto(foto, empresa_codigo, ticket_id):
    """Guarda la imagen normalizada + su miniatura. Devuelve los datos para la BD."""
    carpeta_relativa = f"uploads/{empresa_codigo}/{ticket_id}"
    carpeta = os.path.join(carpeta_proyecto(), *carpeta_relativa.split("/"))
    os.makedirs(carpeta, exist_ok=True)

    mime = foto["mime_type"]
    formato, extension = FORMATO_POR_MIME[mime]
    nombre_base = uuid.uuid4().hex          # nombre imposible de adivinar o repetir

    with Image.open(io.BytesIO(foto["contenido"])) as original:
        img = ImageOps.exif_transpose(original)    # respeta la rotación del celular
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))  # reduce solo si es más grande

        destino = os.path.join(carpeta, f"{nombre_base}.{extension}")
        if formato == "JPEG":
            _a_rgb(img).save(destino, "JPEG", quality=85, optimize=True)
        elif formato == "PNG":
            img.save(destino, "PNG", optimize=True)
        else:
            img.save(destino, "WEBP", quality=85)

        # Si un PNG enorme quedó en más de 5 MB, se guarda como JPEG
        if os.path.getsize(destino) > TAMANO_MAXIMO:
            os.remove(destino)
            mime, extension = "image/jpeg", "jpg"
            destino = os.path.join(carpeta, f"{nombre_base}.jpg")
            _a_rgb(img).save(destino, "JPEG", quality=80, optimize=True)

        miniatura = ImageOps.fit(_a_rgb(img), TAMANO_MINIATURA, Image.Resampling.LANCZOS)
        miniatura.save(os.path.join(carpeta, f"{nombre_base}_min.jpg"), "JPEG", quality=80)

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
    shutil.rmtree(os.path.join(carpeta_proyecto(), "uploads", empresa_codigo, str(ticket_id)),
                  ignore_errors=True)


# =====================================================================
# 4. SEGURIDAD: usuario de la sesión y permisos
# =====================================================================
# El login (run.py) guarda en session: usuario_id, empresa_id, nombre, rol.
# Aquí se vuelve a leer el usuario de la BD para confirmar que sigue activo.
ROL_ADMIN = "Administrador"
ROL_TECNICO = "Técnico"
ROL_SOLICITANTE = "Solicitante"


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario_id = session.get("usuario_id")
        if not usuario_id:
            return jsonify(error="Tu sesión expiró. Vuelve a iniciar sesión."), 401
        with conexion().cursor() as cur:
            cur.execute(
                """SELECT id, nombre, correo, rol, activo, empresa_id, empresa,
                          empresa_codigo, area_id, area, empresa_activa
                     FROM v_usuarios_sesion WHERE id = %s""",
                (usuario_id,),
            )
            usuario = cur.fetchone()
        if not usuario or not usuario["activo"] or not usuario["empresa_activa"]:
            session.clear()
            return jsonify(error="Usuario inactivo. Vuelve a iniciar sesión."), 401
        g.usuario = usuario
        return vista(*args, **kwargs)
    return envoltura


def puede_ver(usuario, ticket):
    """La empresa ya se filtra en la consulta; el solicitante solo ve los suyos."""
    return usuario["rol"] != ROL_SOLICITANTE or ticket["solicitante_id"] == usuario["id"]


def puede_editar(usuario, ticket):
    """Admin (si no está cerrado). Solicitante: su ticket mientras siga 'Abierto'."""
    if ticket["estado"] == "Cerrado":
        return False
    if usuario["rol"] == ROL_ADMIN:
        return True
    return ticket["solicitante_id"] == usuario["id"] and ticket["estado"] == "Abierto"


def puede_adjuntar(usuario, ticket):
    """Subir fotos: dueño del ticket, técnico o admin, mientras no esté cerrado."""
    if ticket["estado"] == "Cerrado":
        return False
    return usuario["rol"] in (ROL_ADMIN, ROL_TECNICO) or ticket["solicitante_id"] == usuario["id"]


def puede_eliminar(usuario, ticket):
    """Admin siempre; solicitante solo si sigue 'Abierto' y sin técnico asignado."""
    if usuario["rol"] == ROL_ADMIN:
        return True
    return (ticket["solicitante_id"] == usuario["id"] and ticket["estado"] == "Abierto"
            and ticket["tecnico_id"] is None)


# =====================================================================
# 5. CONTROLADOR: API JSON
# =====================================================================
#   GET    /api/tickets/sesion                   usuario + catálogos del formulario
#   POST   /api/tickets                          crear ticket + hasta 3 fotos (multipart)
#   GET    /api/tickets                          listado con miniatura
#   GET    /api/tickets/<id>                     detalle con evidencias
#   PUT    /api/tickets/<id>                     editar ticket
#   DELETE /api/tickets/<id>                     eliminar ticket
#   POST   /api/tickets/<id>/evidencias          agregar fotos (máx. 3 en total)
#   DELETE /api/tickets/<id>/evidencias/<eid>    quitar una foto
#   GET    /api/evidencias/<eid>/miniatura|imagen  archivo protegido por sesión
@tickets_bp.record_once
def _configurar(state):
    app = state.app
    # Límite de la petición completa: 3 fotos x 5 MB + campos del formulario
    if not app.config.get("MAX_CONTENT_LENGTH"):
        app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@tickets_bp.app_errorhandler(RequestEntityTooLarge)
def _demasiado_grande(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Los archivos superan el tamaño total permitido (16 MB)."), 413
    return error


@tickets_bp.errorhandler(pymysql.MySQLError)
def _error_mysql(error):
    """Los triggers usan SIGNAL (código 1644) con un mensaje para el usuario."""
    if error.args and error.args[0] == 1644:
        return jsonify(error=error.args[1]), 400
    current_app.logger.exception("Error de base de datos en tickets")
    return jsonify(error="Error de base de datos. Inténtalo nuevamente."), 500


def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor else None


def _urls_evidencia(evidencia_id):
    return {
        "miniatura_url": url_for("tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="miniatura"),
        "imagen_url": url_for("tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="imagen"),
    }


def _ticket_base(t):
    return {
        "id": t["id"], "codigo": t["codigo"], "asunto": t["asunto"], "empresa": t["empresa"],
        "categoria_id": t["categoria_id"], "categoria": t["categoria"],
        "area_id": t["area_id"], "area": t["area"],
        "prioridad_id": t["prioridad_id"], "prioridad": t["prioridad"], "sla_horas": t["sla_horas"],
        "estado": t["estado"],
        "solicitante_id": t["solicitante_id"], "solicitante": t["solicitante"],
        "tecnico_id": t["tecnico_id"], "tecnico": t["tecnico"] if t["tecnico_id"] else None,
        "created_at": _fecha(t["created_at"]), "fecha_limite": _fecha(t["fecha_limite"]),
        # Calculados por la vista v_tickets (módulo SLA)
        "semaforo": t["semaforo"], "minutos_restantes": t["minutos_restantes"],
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
    datos["evidencias"] = [{
        "id": e["id"], "orden": e["orden"], "nombre": e["nombre_original"],
        "mime_type": e["mime_type"], "tamano_bytes": e["tamano_bytes"],
        "subido_por": e["subido_por"], "subido_por_id": e["subido_por_id"],
        "created_at": _fecha(e["created_at"]), **_urls_evidencia(e["id"]),
    } for e in Evidencia.listar_por_ticket(t["id"])]
    datos["max_evidencias"] = Evidencia.MAX_POR_TICKET
    datos["permisos"] = {
        "editar": puede_editar(usuario, t),
        "adjuntar": puede_adjuntar(usuario, t),
        "eliminar": puede_eliminar(usuario, t),
    }
    return datos


def _fotos_de_la_peticion():
    """Archivos del campo 'fotos' (flask.request.files); se ignoran los vacíos."""
    return [a for a in request.files.getlist("fotos") if a and a.filename]


def _ticket_o_error(ticket_id):
    ticket = Ticket.obtener(ticket_id, g.usuario["empresa_id"])
    if ticket is None:
        return None, (jsonify(error="El ticket no existe."), 404)
    if not puede_ver(g.usuario, ticket):
        return None, (jsonify(error="No tienes acceso a este ticket."), 403)
    return ticket, None


def _guardar_fotos(cur, ticket_id, fotos, guardadas):
    """Guarda cada foto en disco y en la BD usando los 'orden' libres (1, 2, 3)."""
    libres = [n for n in range(1, Evidencia.MAX_POR_TICKET + 1)
              if n not in Evidencia.ordenes_usados(cur, ticket_id)]
    for foto, orden in zip(fotos, libres):
        info = guardar_foto(foto, g.usuario["empresa_codigo"], ticket_id)
        guardadas.append(info["ruta"])
        Evidencia.insertar(cur, ticket_id, orden, info, g.usuario["id"])


@tickets_bp.get("/api/tickets/sesion")
@login_requerido
def sesion_actual():
    u = g.usuario
    return jsonify(
        usuario={"id": u["id"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"],
                 "empresa": u["empresa"], "area_id": u["area_id"], "area": u["area"]},
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
    datos, errores = Ticket.validar(request.form, g.usuario)
    archivos = _fotos_de_la_peticion()
    if len(archivos) > Evidencia.MAX_POR_TICKET:
        errores["fotos"] = f"Puedes adjuntar como máximo {Evidencia.MAX_POR_TICKET} fotos."
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400

    # Se validan TODAS las fotos antes de escribir en disco o en la BD
    try:
        fotos = [validar_foto(a) for a in archivos]
    except ErrorEvidencia as e:
        return jsonify(error=str(e), errores={"fotos": str(e)}), 415

    con = conexion()
    ticket_id = None
    try:
        with con.cursor() as cur:
            # Solicitante automático: sale de la sesión, nunca del formulario
            ticket_id = Ticket.crear(cur, datos, g.usuario["id"])
            _guardar_fotos(cur, ticket_id, fotos, [])
        con.commit()
    except Exception:
        con.rollback()
        if ticket_id:  # no deja fotos huérfanas en /uploads
            borrar_carpeta_ticket(g.usuario["empresa_codigo"], ticket_id)
        raise

    ticket = _ticket_detalle(Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario)
    return jsonify(mensaje=f"Ticket {ticket['codigo']} registrado.", ticket=ticket), 201, {
        "Location": url_for("tickets.obtener_ticket", ticket_id=ticket_id)
    }


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
    if not puede_editar(g.usuario, ticket):
        return jsonify(error="Solo puedes editar tus tickets mientras estén «Abierto»."), 403

    datos, errores = Ticket.validar(request.get_json(silent=True) or request.form, g.usuario)
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400

    con = conexion()
    with con.cursor() as cur:
        Ticket.actualizar(cur, ticket_id, datos)
    con.commit()
    return jsonify(mensaje="Ticket actualizado.",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario))


@tickets_bp.delete("/api/tickets/<int:ticket_id>")
@login_requerido
def eliminar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not puede_eliminar(g.usuario, ticket):
        return jsonify(error="Este ticket ya está en atención y no se puede eliminar."), 403

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
                msg = (f"El ticket ya tiene {actuales} foto(s). "
                       f"Solo puedes agregar {max(disponibles, 0)} más.")
                return jsonify(error=msg, errores={"fotos": msg}), 409
            _guardar_fotos(cur, ticket_id, fotos, guardadas)
        con.commit()
    except Exception:
        con.rollback()
        borrar_archivos(guardadas)
        raise

    return jsonify(mensaje=f"{len(fotos)} foto(s) agregada(s).",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario)), 201


@tickets_bp.delete("/api/tickets/<int:ticket_id>/evidencias/<int:evidencia_id>")
@login_requerido
def eliminar_evidencia(ticket_id, evidencia_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    evidencia = Evidencia.obtener(evidencia_id)
    if evidencia is None or evidencia["ticket_id"] != ticket_id:
        return jsonify(error="La foto no existe."), 404
    if not (puede_editar(g.usuario, ticket) or
            (evidencia["subido_por"] == g.usuario["id"] and ticket["estado"] != "Cerrado")):
        return jsonify(error="No puedes quitar esta foto."), 403

    con = conexion()
    with con.cursor() as cur:
        Evidencia.eliminar(cur, evidencia_id)
    con.commit()
    borrar_archivos([evidencia["ruta"]])
    return jsonify(mensaje="Foto eliminada.",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id, g.usuario["empresa_id"]), g.usuario))


@tickets_bp.get("/api/evidencias/<int:evidencia_id>/<any(miniatura, imagen):tipo>")
@login_requerido
def ver_evidencia(evidencia_id, tipo):
    evidencia = Evidencia.obtener(evidencia_id)
    ticket = evidencia and Ticket.obtener(evidencia["ticket_id"], g.usuario["empresa_id"])
    if not ticket:
        return jsonify(error="La foto no existe."), 404
    if not puede_ver(g.usuario, ticket):
        return jsonify(error="No tienes acceso a esta foto."), 403

    if tipo == "miniatura":
        ruta, mime = ruta_miniatura(evidencia["ruta"]), "image/jpeg"
    else:
        ruta, mime = evidencia["ruta"], evidencia["mime_type"]
    # send_from_directory impide salir de la carpeta del proyecto (protege de "../")
    respuesta = send_from_directory(carpeta_proyecto(), ruta, mimetype=mime, max_age=0)
    respuesta.headers["Cache-Control"] = "private, max-age=600"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta
