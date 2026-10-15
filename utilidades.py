import os
import uuid
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

# ---------------------------------------------
# Listas fijas del sistema
# ---------------------------------------------
EMPRESAS = ["Grupo M&M", "Agrofutura", "EPSEL", "Robotic Air Systems", "Atlántica", "Angel Divino Bus"]
AREAS = ["Administración", "Logística", "Operaciones", "Comercial"]
CATEGORIAS = ["Hardware", "Software", "Red e internet", "Accesos y cuentas", "Impresoras", "Correo"]
PRIORIDADES = ["Alta", "Media", "Baja"]
ESTADOS = ["Abierto", "En proceso", "Resuelto", "Cerrado"]
ESTADOS_CIERRE = ("Resuelto", "Cerrado")
ROLES = ["Administrador", "Técnico", "Solicitante"]

# ---------------------------------------------
# Módulo 4: SLA
# ---------------------------------------------
HORAS_SLA = {"Alta": 4, "Media": 24, "Baja": 72}   # tiempo máximo de resolución
UMBRAL_AMARILLO = 0.75                             # desde el 75 % del plazo el semáforo es amarillo

# ---------------------------------------------
# Módulo 2: fotos de evidencia
# ---------------------------------------------
CARPETA_UPLOADS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
MAX_FOTOS = 3
MAX_MB_FOTO = 5
TIPOS_IMAGEN = {"image/jpeg": "jpg", "image/png": "png"}
FORMATOS_PIL = {"JPEG": "image/jpeg", "PNG": "image/png"}
TAM_MINIATURA = (240, 240)


class ErrorNegocio(Exception):
    """Error de validación o de una regla del sistema, con el código HTTP a devolver."""

    def __init__(self, mensaje, status=400, campos=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.campos = campos or {}


def ahora():
    return datetime.now().replace(microsecond=0)


def duracion(segundos):
    minutos = max(1, round(segundos / 60))
    if minutos < 60:
        return str(minutos) + " min"
    horas, resto_min = divmod(minutos, 60)
    if horas < 24:
        if horas < 10 and resto_min:
            return str(horas) + " h " + str(resto_min) + " min"
        return str(horas) + " h"
    dias, resto_h = divmod(horas, 24)
    if resto_h:
        return str(dias) + " d " + str(resto_h) + " h"
    return str(dias) + " d"


def calcular_sla(ticket):
    """Devuelve el color del semáforo (verde, amarillo o rojo) y un texto para mostrar."""
    limite = HORAS_SLA[ticket["prioridad"]] * 3600
    creado = ticket["created_at"]
    sla = {"limite": limite, "horas_limite": HORAS_SLA[ticket["prioridad"]]}

    if ticket["cerrado_at"]:
        total = (ticket["cerrado_at"] - creado).total_seconds()
        a_tiempo = total <= limite
        sla.update(nivel="verde" if a_tiempo else "rojo",
                   texto="Cumplido" if a_tiempo else "Fuera de plazo",
                   cerrado=True, transcurrido=total, ratio=total / limite)
        return sla

    transcurrido = (ahora() - creado).total_seconds()
    ratio = transcurrido / limite
    if ratio >= 1:
        sla.update(nivel="rojo", texto="Vencido hace " + duracion(transcurrido - limite))
    elif ratio >= UMBRAL_AMARILLO:
        sla.update(nivel="amarillo", texto="Quedan " + duracion(limite - transcurrido))
    else:
        sla.update(nivel="verde", texto="Quedan " + duracion(limite - transcurrido))
    sla.update(cerrado=False, transcurrido=transcurrido, ratio=ratio)
    return sla


def iniciales(nombre):
    return "".join(p[0] for p in (nombre or "?").split()[:2]).upper()


def fecha_iso(fecha):
    return fecha.isoformat() if fecha else None


# ---------------------------------------------
# Fotos: validación MIME, guardado en /uploads y miniaturas
# ---------------------------------------------
def validar_fotos(archivos):
    """Revisa cantidad, tipo y tamaño. Devuelve [(bytes, mime, nombre)] sin guardar nada todavía."""
    archivos = [a for a in archivos if a and a.filename]
    if len(archivos) > MAX_FOTOS:
        raise ErrorNegocio("Solo puedes adjuntar hasta " + str(MAX_FOTOS) + " fotos.", 422,
                           {"fotos": "Máximo " + str(MAX_FOTOS) + " fotos."})

    validas = []
    for archivo in archivos:
        datos = archivo.read()
        nombre = os.path.basename(archivo.filename)[:200]
        if archivo.mimetype not in TIPOS_IMAGEN:
            raise ErrorNegocio('"' + nombre + '" no es una imagen JPG o PNG.', 422, {"fotos": "Solo imágenes JPG o PNG."})
        if len(datos) > MAX_MB_FOTO * 1024 * 1024:
            raise ErrorNegocio('"' + nombre + '" pesa más de 5 MB.', 422, {"fotos": "Cada foto debe pesar menos de 5 MB."})
        # Se abre la imagen para confirmar que de verdad es una imagen (no solo la extensión)
        try:
            with Image.open(BytesIO(datos)) as img:
                formato = img.format
                img.verify()
        except Exception:
            raise ErrorNegocio('"' + nombre + '" está dañada o no es una imagen.', 422, {"fotos": "Archivo de imagen no válido."})
        if formato not in FORMATOS_PIL:
            raise ErrorNegocio('"' + nombre + '" no es una imagen JPG o PNG.', 422, {"fotos": "Solo imágenes JPG o PNG."})
        validas.append((datos, FORMATOS_PIL[formato], nombre))
    return validas


def guardar_fotos(validas):
    """Guarda las imágenes validadas en /uploads con su miniatura. Devuelve los datos para la BD."""
    os.makedirs(CARPETA_UPLOADS, exist_ok=True)
    fotos = []
    for datos, mime, nombre in validas:
        base = uuid.uuid4().hex
        archivo = base + "." + TIPOS_IMAGEN[mime]
        miniatura = base + "_min.jpg"
        with open(os.path.join(CARPETA_UPLOADS, archivo), "wb") as f:
            f.write(datos)
        with Image.open(BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail(TAM_MINIATURA)
            img.convert("RGB").save(os.path.join(CARPETA_UPLOADS, miniatura), "JPEG", quality=82)
        fotos.append({"archivo": archivo, "miniatura": miniatura, "nombre_original": nombre, "mime": mime})
    return fotos


def eliminar_archivos(fotos):
    for foto in fotos:
        for nombre in (foto["archivo"], foto["miniatura"]):
            try:
                os.remove(os.path.join(CARPETA_UPLOADS, nombre))
            except OSError:
                pass


def imagen_de_ejemplo(texto, color):
    """Imagen simple para los datos de prueba."""
    img = Image.new("RGB", (960, 640), color)
    dibujo = ImageDraw.Draw(img)
    dibujo.rectangle((380, 220, 580, 380), outline="#3F4C8C", width=8)
    dibujo.ellipse((420, 250, 460, 290), outline="#3F4C8C", width=6)
    dibujo.line((390, 370, 470, 300, 520, 340, 570, 290), fill="#3F4C8C", width=8)
    dibujo.text((40, 590), texto, fill="#3F4C8C")
    salida = BytesIO()
    img.save(salida, "JPEG", quality=85)
    return salida.getvalue()
