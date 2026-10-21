"""
Tickets — registro de tickets con evidencias fotográficas (Flask + MySQL).
Contenido (patrón MVC):
    1. Conexión a MySQL
    2. Modelo: clases Usuario, Ticket y Evidencia
    3. Fotos de evidencia: validación MIME, guardado en /uploads y miniaturas
    4. Seguridad: usuario autenticado mediante sesión Flask y permisos por rol
    5. Controlador: rutas (página + API JSON)
Se registra en run.py con:  app.register_blueprint(tickets_bp)
"""

import io
import os
import shutil
import uuid
import warnings
from functools import wraps

import pymysql
from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

tickets_bp = Blueprint("tickets", __name__)


# =====================================================================*

# 1. CONEXIÓN A MYSQL*

# =====================================================================*

def obtener_conexion():

    """Una conexión por petición HTTP, guardada en flask.g."""

    if "db_tickets" not in g:
        cfg = current_app.config
        g.db_tickets = pymysql.connect(
            host=cfg.get("DB_HOST", "localhost"),
            port=int(cfg.get("DB_PORT", 3306)),
            user=cfg.get("DB_USER", "root"),
            password=cfg.get("DB_PASSWORD", ""),
            database=cfg.get("DB_NAME", "mesa_ayuda_ti"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,  #* usamos transacciones explícitas*
        )

    return g.db_tickets





def cerrar_conexion(_error=None):
    conexion = g.pop("db_tickets", None)
    if conexion is not None:
        conexion.close()



# =====================================================================*

# 2. MODELO: Usuario, Ticket, Evidencia*

# =====================================================================*

# Código visible del ticket: TK-0001, TK-0002... (se calcula, no se guarda)*

SQL_CODIGO = "CONCAT('TK-', LPAD(t.id, 4, '0'))"





class Usuario:
    @staticmethod
    def obtener(usuario_id):
        with obtener_conexion().cursor() as cur:
            cur.execute(
                """
                SELECT id, empresa_id, nombre, correo, rol, activo
                FROM users
                WHERE id = %s
                """,
                (usuario_id,),
            )
            return cur.fetchone()





class Ticket:
    ESTADOS = ("Abierto", "En proceso", "Resuelto", "Cerrado")
    CAMPOS = ("asunto", "descripcion", "categoria", "area", "prioridad")

    @classmethod
    def validar(cls, datos, empresa_id):
        """Valida los campos y verifica los catálogos en la BD."""
        limpios = {c: (datos.get(c) or "").strip() for c in cls.CAMPOS}
        errores = {}

        if not 5 <= len(limpios["asunto"]) <= 120:
            errores["asunto"] = "El asunto debe tener entre 5 y 120 caracteres."
        if not 10 <= len(limpios["descripcion"]) <= 1000:
            errores["descripcion"] = "La descripción debe tener entre 10 y 1000 caracteres."

        ids = {}
        for campo in ("categoria", "area", "prioridad"):
            try:
                ids[campo] = int(limpios[campo])
                if ids[campo] <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                ids[campo] = None
                errores[campo] = f"Selecciona una {campo} válida."

        with obtener_conexion().cursor() as cur:
            if ids["categoria"] is not None:
                cur.execute(
                    "SELECT id FROM categorias WHERE id=%s AND activo=1",
                    (ids["categoria"],),
                )
                if cur.fetchone() is None:
                    errores["categoria"] = "Selecciona una categoría válida."

            if ids["area"] is not None:
                cur.execute(
                    "SELECT id FROM areas WHERE id=%s AND empresa_id=%s AND activo=1",
                    (ids["area"], empresa_id),
                )
                if cur.fetchone() is None:
                    errores["area"] = "El área no es válida para tu empresa."

            if ids["prioridad"] is not None:
                cur.execute("SELECT id FROM prioridades WHERE id=%s", (ids["prioridad"],))
                if cur.fetchone() is None:
                    errores["prioridad"] = "Selecciona una prioridad válida."

        if not errores:
            limpios["categoria_id"] = ids["categoria"]
            limpios["area_id"] = ids["area"]
            limpios["prioridad_id"] = ids["prioridad"]
        return limpios, errores

    @staticmethod
    def crear(cur, datos, solicitante_id, empresa_id):
        cur.execute(
            """INSERT INTO tickets
               (empresa_id, area_id, solicitante_id, categoria_id, prioridad_id,
                asunto, descripcion, estado)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'Abierto')""",
            (
                empresa_id, datos["area_id"], solicitante_id,
                datos["categoria_id"], datos["prioridad_id"],
                datos["asunto"], datos["descripcion"],
            ),
        )
        return cur.lastrowid

    @staticmethod
    def actualizar(cur, ticket_id, datos, empresa_id):
        cur.execute(
            """UPDATE tickets
               SET asunto=%s, descripcion=%s, categoria_id=%s,
                   area_id=%s, prioridad_id=%s
               WHERE id=%s AND empresa_id=%s""",
            (
                datos["asunto"], datos["descripcion"], datos["categoria_id"],
                datos["area_id"], datos["prioridad_id"], ticket_id, empresa_id,
            ),
        )

    @staticmethod
    def eliminar(cur, ticket_id, empresa_id):
        cur.execute(
            "DELETE FROM tickets WHERE id=%s AND empresa_id=%s",
            (ticket_id, empresa_id),
        )

    @staticmethod
    def bloquear(cur, ticket_id, empresa_id):
        cur.execute(
            "SELECT id FROM tickets WHERE id=%s AND empresa_id=%s FOR UPDATE",
            (ticket_id, empresa_id),
        )
        return cur.fetchone() is not None

    @staticmethod
    def obtener(ticket_id):
        with obtener_conexion().cursor() as cur:
            cur.execute(
                f"""SELECT t.id, {SQL_CODIGO} AS codigo, t.empresa_id,
                           t.area_id, t.numero, t.asunto, t.descripcion,
                           c.nombre AS categoria, a.nombre AS area,
                           p.nombre AS prioridad, t.estado,
                           t.solicitante_id, u.nombre AS solicitante,
                           t.tecnico_id, tec.nombre AS tecnico,
                           t.fecha_limite, t.created_at, t.updated_at
                    FROM tickets t
                    JOIN users u ON u.id=t.solicitante_id
                    LEFT JOIN users tec ON tec.id=t.tecnico_id
                    LEFT JOIN categorias c ON c.id=t.categoria_id
                    LEFT JOIN areas a ON a.id=t.area_id
                    LEFT JOIN prioridades p ON p.id=t.prioridad_id
                    WHERE t.id=%s""",
                (ticket_id,),
            )
            return cur.fetchone()

    @staticmethod
    def listar(usuario, filtros):
        condiciones = ["t.empresa_id=%s"]
        params = [usuario["empresa_id"]]
        if usuario["rol"] == ROL_SOLICITANTE:
            condiciones.append("t.solicitante_id=%s")
            params.append(usuario["id"])
        elif usuario["rol"] == ROL_TECNICO:
            # El técnico ve los tickets asignados y los aún no asignados de su empresa.
            condiciones.append("(t.tecnico_id=%s OR t.tecnico_id IS NULL)")
            params.append(usuario["id"])
        elif filtros.get("mios"):
            condiciones.append("(t.solicitante_id=%s OR t.tecnico_id=%s)")
            params.extend([usuario["id"], usuario["id"]])
        if filtros.get("estado") in Ticket.ESTADOS:
            condiciones.append("t.estado=%s")
            params.append(filtros["estado"])
        if filtros.get("prioridad"):
            condiciones.append("p.nombre=%s")
            params.append(filtros["prioridad"])
        if filtros.get("categoria"):
            condiciones.append("c.nombre=%s")
            params.append(filtros["categoria"])
        if filtros.get("q"):
            condiciones.append(f"(t.asunto LIKE %s OR {SQL_CODIGO} LIKE %s)")
            q = f"%{filtros['q']}%"
            params.extend([q, q])
        params.append(filtros.get("limite", 50))
        with obtener_conexion().cursor() as cur:
            cur.execute(
                f"""SELECT t.id, {SQL_CODIGO} AS codigo, t.empresa_id,
                           t.asunto, c.nombre AS categoria, a.nombre AS area,
                           p.nombre AS prioridad, t.estado, t.created_at,
                           u.nombre AS solicitante, tec.nombre AS tecnico,
                           (SELECT COUNT(*) FROM ticket_evidencias e
                             WHERE e.ticket_id=t.id) AS total_evidencias,
                           (SELECT MIN(e.id) FROM ticket_evidencias e
                             WHERE e.ticket_id=t.id) AS primera_evidencia_id
                    FROM tickets t
                    JOIN users u ON u.id=t.solicitante_id
                    LEFT JOIN users tec ON tec.id=t.tecnico_id
                    LEFT JOIN categorias c ON c.id=t.categoria_id
                    LEFT JOIN areas a ON a.id=t.area_id
                    LEFT JOIN prioridades p ON p.id=t.prioridad_id
                    WHERE {" AND ".join(condiciones)}
                    ORDER BY t.created_at DESC, t.id DESC LIMIT %s""",
                params,
            )
            return cur.fetchall()


class Evidencia:
    MAX_POR_TICKET = 3
    @staticmethod

    def contar(cur, ticket_id):
        cur.execute("SELECT COUNT(*) AS total FROM ticket_evidencias WHERE ticket_id = %s",
                    (ticket_id,))
        return cur.fetchone()["total"]



    @staticmethod
    def insertar(cur, ticket_id, info, subido_por):
        cur.execute(
            """INSERT INTO ticket_evidencias
                 (ticket_id, nombre_original, archivo, miniatura, mime_type,
                  tamano_bytes, ancho, alto, subido_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (ticket_id, info["nombre_original"], info["archivo"], info["miniatura"],

             info["mime_type"], info["tamano_bytes"], info["ancho"], info["alto"], subido_por),
        )
        return cur.lastrowid



    @staticmethod
    def listar_por_ticket(ticket_id):
        with obtener_conexion().cursor() as cur:
            cur.execute(
                """SELECT e.id, e.ticket_id, e.nombre_original, e.mime_type, e.tamano_bytes,
                          e.ancho, e.alto, e.created_at, u.nombre AS subido_por
                     FROM ticket_evidencias e
                     JOIN users u ON u.id = e.subido_por
                    WHERE e.ticket_id = %s
                    ORDER BY e.id""",
                (ticket_id,),
            )
            return cur.fetchall()


    @staticmethod
    def obtener(evidencia_id):
        with obtener_conexion().cursor() as cur:
            cur.execute("SELECT * FROM ticket_evidencias WHERE id = %s", (evidencia_id,))
            return cur.fetchone()



    @staticmethod
    def eliminar(cur, evidencia_id):
        cur.execute("DELETE FROM ticket_evidencias WHERE id = %s", (evidencia_id,))



# =====================================================================*

# 3. FOTOS DE EVIDENCIA*

# =====================================================================*

# Validación en 4 capas: extensión, MIME declarado, MIME REAL por firma*

# binaria (magic numbers) y decodificación con Pillow. Las imágenes se*

# re-guardan con Pillow (sin metadatos EXIF) en uploads/tickets/<id>/.*

EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}
MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANO_MAXIMO = 5 * 1024 * 1024        #* 5 MB por foto*
LADO_MAXIMO = 1920                     #* px de la imagen completa guardada*
TAMANO_MINIATURA = (240, 240)          #* px de la miniatura del listado*
Image.MAX_IMAGE_PIXELS = 40_000_000    #* protege contra "bombas" de descompresión*



# Formato de Pillow y extensión con la que se guarda cada tipo MIME*

FORMATO_POR_MIME = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}





class ErrorEvidencia(ValueError):
    """Error de validación de una foto (se muestra tal cual al usuario)."""
def detectar_mime_real(cabecera: bytes):
    """Devuelve el tipo MIME según los primeros bytes del archivo, o None.
        JPEG: FF D8 FF
        PNG : 89 50 4E 47 0D 0A 1A 0A
        WEBP: 'RIFF' + 4 bytes de tamaño + 'WEBP'
    """

    if cabecera[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if cabecera[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return None





def validar_foto(archivo):
    """Valida un FileStorage de request.files.
    Devuelve un dict con los bytes y el MIME real, o lanza ErrorEvidencia.
    """
    nombre = archivo.filename or "archivo"



    #* 1) Extensión*

    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorEvidencia(f"«{nombre}»: solo se permiten imágenes JPG, PNG o WEBP.")



    #* 2) MIME declarado por el navegador*

    if (archivo.mimetype or "").lower() not in MIME_PERMITIDOS:
        raise ErrorEvidencia(f"«{nombre}»: el tipo de archivo no es una imagen permitida.")



    #* Leemos como máximo TAMANO_MAXIMO + 1 bytes para no cargar archivos enormes*

    contenido = archivo.stream.read(TAMANO_MAXIMO + 1)
    if len(contenido) == 0:
        raise ErrorEvidencia(f"«{nombre}»: el archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ErrorEvidencia(f"«{nombre}»: supera el máximo de 5 MB.")



    #* 3) MIME real por firma binaria*

    mime_real = detectar_mime_real(contenido[:12])
    if mime_real is None:
        raise ErrorEvidencia(f"«{nombre}»: el contenido no es una imagen real (firma no válida).")



    #* 4) Pillow debe poder abrirla y su formato debe coincidir con la firma*

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
    return {"nombre_original": nombre, "contenido": contenido, "mime_type": mime_real}





def _a_rgb(img):

    """Convierte a RGB; si la imagen tiene transparencia la pone sobre blanco."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.split()[-1])
        return fondo
    return img.convert("RGB")





def guardar_foto(foto, carpeta_uploads, ticket_id):
    """Guarda la imagen normalizada + su miniatura. Devuelve los datos para la BD."""
    carpeta_relativa = os.path.join("tickets", str(ticket_id))
    carpeta = os.path.join(carpeta_uploads, carpeta_relativa)
    os.makedirs(carpeta, exist_ok=True)
    formato, extension = FORMATO_POR_MIME[foto["mime_type"]]
    nombre_base = uuid.uuid4().hex          #* nombre imposible de adivinar/colisionar*
    nombre_imagen = f"{nombre_base}.{extension}"
    nombre_miniatura = f"{nombre_base}_min.jpg"

    with Image.open(io.BytesIO(foto["contenido"])) as original:
        img = ImageOps.exif_transpose(original)   #* respeta la rotación del celular*
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO)) #* reduce solo si es más grande*

        if formato == "JPEG":
            img = _a_rgb(img)
            img.save(os.path.join(carpeta, nombre_imagen), "JPEG", quality=85, optimize=True)
        elif formato == "PNG":
            img.save(os.path.join(carpeta, nombre_imagen), "PNG", optimize=True)
        else:
            img.save(os.path.join(carpeta, nombre_imagen), "WEBP", quality=85)

        miniatura = ImageOps.fit(_a_rgb(img), TAMANO_MINIATURA, Image.Resampling.LANCZOS)
        miniatura.save(os.path.join(carpeta, nombre_miniatura), "JPEG", quality=80)
        ancho, alto = img.size

    ruta_imagen = os.path.join(carpeta, nombre_imagen)

    return {
        "nombre_original": secure_filename(foto["nombre_original"]) or nombre_imagen,
        "archivo": f"{carpeta_relativa}/{nombre_imagen}".replace(os.sep, "/"),
        "miniatura": f"{carpeta_relativa}/{nombre_miniatura}".replace(os.sep, "/"),
        "mime_type": foto["mime_type"],
        "tamano_bytes": os.path.getsize(ruta_imagen),
        "ancho": ancho,
        "alto": alto,
    }





def borrar_archivos(carpeta_uploads, rutas_relativas):
    for ruta in rutas_relativas:
        try:
            os.remove(os.path.join(carpeta_uploads, ruta))
        except FileNotFoundError:
            pass


def borrar_carpeta_ticket(carpeta_uploads, ticket_id):
    shutil.rmtree(os.path.join(carpeta_uploads, "tickets", str(ticket_id)), ignore_errors=True)



# =====================================================================*

# 4. SEGURIDAD: usuario del token y permisos*

# =====================================================================*

# El usuario sale de la sesión Flask.*

# El módulo utiliza la sesión del login principal.*

ROL_ADMIN = "Administrador"
ROL_TECNICO = "Técnico"
ROL_SOLICITANTE = "Solicitante"







def _id_desde_token():
    """Devuelve el ID del usuario autenticado mediante la sesión Flask."""
    usuario_id = session.get("usuario_id")

    if usuario_id is None:
        return None

    try:
        return int(usuario_id)
    except (TypeError, ValueError):
        return None









def login_requerido(*roles_permitidos):
    """Exige una sesión autenticada y un usuario activo."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            usuario_id = _id_desde_token()

            if usuario_id is None:
                return jsonify(error="Debes iniciar sesión."), 401
            usuario = Usuario.obtener(usuario_id)
            if usuario is None or not usuario["activo"]:
                session.clear()
                return jsonify(error="Usuario no encontrado o inactivo."), 401
            if roles_permitidos and usuario["rol"] not in roles_permitidos:
                return jsonify(error="No tienes permiso para esta acción."), 403
            g.usuario = usuario
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def puede_ver(usuario, ticket):
    """Comprueba el acceso al ticket según empresa, rol y asignación."""

    #* Ningún usuario puede acceder a tickets de otra empresa.*

    if usuario["empresa_id"] != ticket["empresa_id"]:
        return False



    #* El administrador ve todos los tickets de su empresa.*

    if usuario["rol"] == ROL_ADMIN:
        return True



    #* El técnico solo ve los tickets asignados a él.*

    if usuario["rol"] == ROL_TECNICO:
        return ticket["tecnico_id"] == usuario["id"]



    #* El solicitante solo ve los tickets que creó.*

    if usuario["rol"] == ROL_SOLICITANTE:
        return ticket["solicitante_id"] == usuario["id"]

    #* Denegar cualquier rol no reconocido.*

    return False







def puede_editar(usuario, ticket):

    """Comprueba si el usuario puede editar el ticket."""
    #* Impedir modificaciones entre empresas.*

    if usuario["empresa_id"] != ticket["empresa_id"]:
        return False



    #* El administrador puede editar cualquier ticket de su empresa.*

    if usuario["rol"] == ROL_ADMIN:
        return True



    #* El solicitante puede editar su ticket mientras esté abierto.*

    if usuario["rol"] == ROL_SOLICITANTE:
        return (
            ticket["solicitante_id"] == usuario["id"]
            and ticket["estado"] == "Abierto"
        )



    #* El técnico no puede editar los datos generales del ticket*

    #* mediante esta función.*

    return False









def puede_adjuntar(usuario, ticket):

    """Comprueba si el usuario puede adjuntar evidencias al ticket."""
    #* Bloquear acceso entre empresas.*

    if usuario["empresa_id"] != ticket["empresa_id"]:
        return False

    #* El administrador puede adjuntar evidencias en su empresa.*

    if usuario["rol"] == ROL_ADMIN:
        return True



    #* El técnico solo puede adjuntar en tickets asignados a él.*

    if usuario["rol"] == ROL_TECNICO:
        return ticket["tecnico_id"] == usuario["id"]



    #* El solicitante puede adjuntar mientras su ticket no esté cerrado.*

    if usuario["rol"] == ROL_SOLICITANTE:
        return (
            ticket["solicitante_id"] == usuario["id"]
            and ticket["estado"] != "Cerrado"
        )

    return False





# =====================================================================*

# 5. CONTROLADOR: rutas*

# =====================================================================*





# ---------------------------------------------------------------------*

# Configuración que el módulo necesita al registrarse en la app*

# ---------------------------------------------------------------------*

@tickets_bp.record_once
def _configurar(state):
    app = state.app
    app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads"))

    #* Límite de la petición completa: 3 fotos x 5 MB + campos del formulario*

    #* (Flask trae MAX_CONTENT_LENGTH=None por defecto, por eso no sirve setdefault)*

    if not app.config.get("MAX_CONTENT_LENGTH"):
        app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.teardown_appcontext(cerrar_conexion)





@tickets_bp.app_errorhandler(RequestEntityTooLarge)
def _demasiado_grande(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Los archivos superan el tamaño total permitido (16 MB)."), 413
    return error





def _carpeta_uploads():
    return current_app.config["UPLOAD_FOLDER"]





# ---------------------------------------------------------------------*

# Conversión a JSON*

# ---------------------------------------------------------------------*

def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor else None





def _urls_evidencia(evidencia_id):
    return {
        "miniatura_url": url_for("tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="miniatura"),
        "imagen_url": url_for("tickets.ver_evidencia", evidencia_id=evidencia_id, tipo="imagen"),
    }





def _ticket_resumen(t):

    datos = {
        "id": t["id"], "codigo": t["codigo"], "asunto": t["asunto"],
        "categoria": t["categoria"], "area": t["area"],
        "prioridad": t["prioridad"], "estado": t["estado"],
        "solicitante": t["solicitante"], "tecnico": t.get("tecnico"),
        "created_at": _fecha(t["created_at"]),
        "total_evidencias": t["total_evidencias"],
        "miniatura_url": None, "imagen_url": None,
    }

    if t["primera_evidencia_id"]:
        datos.update(_urls_evidencia(t["primera_evidencia_id"]))
    return datos





def _ticket_detalle(t, usuario):
    evidencias = []
    for e in Evidencia.listar_por_ticket(t["id"]):
        evidencias.append({
            "id": e["id"], "nombre": e["nombre_original"], "mime_type": e["mime_type"],
            "tamano_bytes": e["tamano_bytes"], "ancho": e["ancho"], "alto": e["alto"],
            "subido_por": e["subido_por"], "created_at": _fecha(e["created_at"]),
            **_urls_evidencia(e["id"]),
        })
    return {
        "id": t["id"], "codigo": t["codigo"], "asunto": t["asunto"],
        "descripcion": t["descripcion"], "categoria": t["categoria"], "area": t["area"],
        "prioridad": t["prioridad"], "estado": t["estado"],
        "solicitante_id": t["solicitante_id"], "solicitante": t["solicitante"],
        "tecnico": t["tecnico"],
        "created_at": _fecha(t["created_at"]), "updated_at": _fecha(t["updated_at"]),
        "evidencias": evidencias,
        "max_evidencias": Evidencia.MAX_POR_TICKET,
        "permisos": {
            "editar": puede_editar(usuario, t),
            "adjuntar": puede_adjuntar(usuario, t),
        },
    }





def _fotos_de_la_peticion():
    """Archivos del campo 'fotos' (se ignoran inputs vacíos)."""
    return [a for a in request.files.getlist("fotos") if a and a.filename]





def _al_crear_ticket(cur, ticket_id, usuario):
    """Punto de integración para otros módulos, dentro de la misma transacción.
    Ej.: módulo 3 -> INSERT en ticket_historial (estado inicial 'Abierto')
         módulo 5 -> INSERT en notificaciones para los administradores."""
    pass





# ---------------------------------------------------------------------*

# Página*

# ---------------------------------------------------------------------*

@tickets_bp.get("/nuevo_ticket.html")
def pagina_nuevo_ticket():
    return render_template("nuevo_ticket.html")





# ---------------------------------------------------------------------*

# API*

# ---------------------------------------------------------------------*

def _catalogos_usuario(usuario):
    """Catálogos activos; las áreas siempre se filtran por empresa."""
    with obtener_conexion().cursor() as cur:
        cur.execute("SELECT id, nombre FROM categorias WHERE activo=1 ORDER BY nombre")
        categorias = cur.fetchall()
        cur.execute(
            "SELECT id, nombre FROM areas WHERE empresa_id=%s AND activo=1 ORDER BY nombre",
            (usuario["empresa_id"],),
        )
        areas = cur.fetchall()
        cur.execute("SELECT id, nombre FROM prioridades ORDER BY nivel")
        prioridades = cur.fetchall()
    return {
        "categorias": categorias,
        "areas": areas,
        "prioridades": prioridades,
        "max_evidencias": Evidencia.MAX_POR_TICKET,
        "max_mb_por_foto": TAMANO_MAXIMO // (1024 * 1024),
    }


@tickets_bp.get("/api/tickets/sesion")

@login_requerido()
def sesion_actual():
    u = g.usuario
    return jsonify(
        usuario={"id": u["id"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"]},
        catalogos={
            "categorias": Ticket.CATEGORIAS, "areas": Ticket.AREAS,
            "prioridades": Ticket.PRIORIDADES,
            "max_evidencias": Evidencia.MAX_POR_TICKET,
            "max_mb_por_foto": TAMANO_MAXIMO // (1024 * 1024),
        },
    )





@tickets_bp.post("/api/tickets")

@login_requerido()
def crear_ticket():
    datos, errores = Ticket.validar(
    request.form,
    g.usuario["empresa_id"],
    )
    archivos = _fotos_de_la_peticion()
    if len(archivos) > Evidencia.MAX_POR_TICKET:
        errores["fotos"] = f"Puedes adjuntar como máximo {Evidencia.MAX_POR_TICKET} fotos."
    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400



    #* Se validan TODAS las fotos antes de escribir nada en disco o BD*

    try:
        fotos = [validar_foto(a) for a in archivos]
    except ErrorEvidencia as e:
        return jsonify(error=str(e), errores={"fotos": str(e)}), 415



    conexion = obtener_conexion()
    ticket_id = None

    try:

        with conexion.cursor() as cur:

            #* Solicitante automático: sale del token, no del formulario*

            ticket_id = Ticket.crear(cur, datos, g.usuario["id"], g.usuario["empresa_id"])
            for foto in fotos:
                info = guardar_foto(foto, _carpeta_uploads(), ticket_id)
                Evidencia.insertar(cur, ticket_id, info, g.usuario["id"])
            _al_crear_ticket(cur, ticket_id, g.usuario)
        conexion.commit()
    except Exception:
        conexion.rollback()
        if ticket_id:  #* si algo falló, no deja fotos huérfanas en /uploads*
            borrar_carpeta_ticket(_carpeta_uploads(), ticket_id)
        raise



    ticket = _ticket_detalle(Ticket.obtener(ticket_id), g.usuario)
    return jsonify(mensaje=f"Ticket {ticket['codigo']} registrado.", ticket=ticket), 201, {
        "Location": url_for("tickets.obtener_ticket", ticket_id=ticket_id)

    }





@tickets_bp.get("/api/tickets")
@login_requerido()
def listar_tickets():
    try:
        limite = max(1, min(int(request.args.get("limite", 50)), 200))
    except ValueError:
        limite = 50
    filtros = {
        "estado": request.args.get("estado"),
        "prioridad": request.args.get("prioridad"),
        "categoria": request.args.get("categoria"),
        "q": (request.args.get("q") or "").strip()[:60],
        "mios": request.args.get("mios") == "1",
        "limite": limite,
    }

    tickets = [_ticket_resumen(t) for t in Ticket.listar(g.usuario, filtros)]
    return jsonify(tickets=tickets, total=len(tickets))







def _ticket_o_error(ticket_id):
    """Devuelve (ticket, None) o (None, respuesta_de_error)."""
    ticket = Ticket.obtener(ticket_id)

    if ticket is None:
        return None, (jsonify(error="El ticket no existe."), 404)

    #* Evitar acceso a tickets de otra empresa.*
    if ticket["empresa_id"] != g.usuario["empresa_id"]:
        return None, (jsonify(error="El ticket no existe."), 404)



    #* Comprobar permisos según el rol del usuario.*
    if not puede_ver(g.usuario, ticket):
        return None, (jsonify(error="No tienes acceso a este ticket."), 403)
    return ticket, None







@tickets_bp.get("/api/tickets/<int:ticket_id>")
@login_requerido()
def obtener_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    return jsonify(ticket=_ticket_detalle(ticket, g.usuario))





@tickets_bp.put("/api/tickets/<int:ticket_id>")
@login_requerido()
def editar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not puede_editar(g.usuario, ticket):
        return jsonify(error="Solo puedes editar tus tickets mientras estén «Abierto»."), 403
    datos, errores = Ticket.validar(request.get_json(silent=True) or request.form, g.usuario["empresa_id"])

    if errores:
        return jsonify(error="Revisa los campos marcados.", errores=errores), 400
    conexion = obtener_conexion()
    with conexion.cursor() as cur:
        Ticket.actualizar(cur, ticket_id, datos, g.usuario["empresa_id"])
    conexion.commit()
    return jsonify(mensaje="Ticket actualizado.",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id), g.usuario))





@tickets_bp.delete("/api/tickets/<int:ticket_id>")
@login_requerido()
def eliminar_ticket(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    #* Admin siempre; el solicitante solo si sigue Abierto y sin técnico asignado*

    es_admin = g.usuario["rol"] == ROL_ADMIN
    if not es_admin and not (puede_editar(g.usuario, ticket) and ticket["tecnico_id"] is None):
        return jsonify(error="Este ticket ya está en atención y no se puede eliminar."), 403



    conexion = obtener_conexion()
    with conexion.cursor() as cur:
        Ticket.eliminar(cur, ticket_id, g.usuario["empresa_id"])
    conexion.commit()
    borrar_carpeta_ticket(_carpeta_uploads(), ticket_id)
    return jsonify(mensaje=f"Ticket {ticket['codigo']} eliminado.")





@tickets_bp.post("/api/tickets/<int:ticket_id>/evidencias")
@login_requerido()
def agregar_evidencias(ticket_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    if not puede_adjuntar(g.usuario, ticket):
        return jsonify(error="No puedes adjuntar fotos a este ticket."), 403
    
    archivos = _fotos_de_la_peticion()
    if not archivos:
        return jsonify(error="Selecciona al menos una foto.", errores={"fotos": "Selecciona al menos una foto."}), 400
    try:
        fotos = [validar_foto(a) for a in archivos]
    except ErrorEvidencia as e:
        return jsonify(error=str(e), errores={"fotos": str(e)}), 415

    conexion = obtener_conexion()
    guardadas = []
    try:
        with conexion.cursor() as cur:
            Ticket.bloquear(cur, ticket_id, g.usuario["empresa_id"])  #* nadie más sube fotos a este ticket ahora*
            actuales = Evidencia.contar(cur, ticket_id)
            disponibles = Evidencia.MAX_POR_TICKET - actuales
            if len(fotos) > disponibles:
                conexion.rollback()
                msg = (f"El ticket ya tiene {actuales} foto(s). "
                       f"Solo puedes agregar {max(disponibles, 0)} más.")
                return jsonify(error=msg, errores={"fotos": msg}), 409
            for foto in fotos:
                info = guardar_foto(foto, _carpeta_uploads(), ticket_id)
                guardadas.append(info)
                Evidencia.insertar(cur, ticket_id, info, g.usuario["id"])
        conexion.commit()
    except Exception:
        conexion.rollback()
        borrar_archivos(_carpeta_uploads(),
                        [r for i in guardadas for r in (i["archivo"], i["miniatura"])])
        raise
    return jsonify(mensaje=f"{len(fotos)} foto(s) agregada(s).",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id), g.usuario)), 201





@tickets_bp.delete("/api/tickets/<int:ticket_id>/evidencias/<int:evidencia_id>")
@login_requerido()

def eliminar_evidencia(ticket_id, evidencia_id):
    ticket, error = _ticket_o_error(ticket_id)
    if error:
        return error
    evidencia = Evidencia.obtener(evidencia_id)
    if evidencia is None or evidencia["ticket_id"] != ticket_id:
        return jsonify(error="La foto no existe."), 404
    if not (puede_editar(g.usuario, ticket) or evidencia["subido_por"] == g.usuario["id"]):
        return jsonify(error="No puedes quitar esta foto."), 403
    conexion = obtener_conexion()
    with conexion.cursor() as cur:
        Evidencia.eliminar(cur, evidencia_id)
    conexion.commit()
    borrar_archivos(_carpeta_uploads(), [evidencia["archivo"], evidencia["miniatura"]])
    return jsonify(mensaje="Foto eliminada.",
                   ticket=_ticket_detalle(Ticket.obtener(ticket_id), g.usuario))





@tickets_bp.get("/api/evidencias/<int:evidencia_id>/<any(miniatura, imagen):tipo>")
@login_requerido()
def ver_evidencia(evidencia_id, tipo):
    evidencia = Evidencia.obtener(evidencia_id)
    if evidencia is None:
        return jsonify(error="La foto no existe."), 404
    ticket = Ticket.obtener(evidencia["ticket_id"])
    if not puede_ver(g.usuario, ticket):
        return jsonify(error="No tienes acceso a esta foto."), 403
    if tipo == "miniatura":
        ruta, mime = evidencia["miniatura"], "image/jpeg"
    else:
        ruta, mime = evidencia["archivo"], evidencia["mime_type"]
    #* send_from_directory impide salir de /uploads (protege de "../")*
    respuesta = send_from_directory(_carpeta_uploads(), ruta, mimetype=mime, max_age=0)
    respuesta.headers["Cache-Control"] = "private, max-age=600"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta
