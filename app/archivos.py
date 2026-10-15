"""Manejo de fotos de evidencia: validación MIME, guardado en /uploads y miniaturas."""
import os
import uuid
from io import BytesIO

from flask import current_app
from PIL import Image, ImageDraw, ImageOps

from .errores import ErrorNegocio
from .models import TicketFoto

TAM_MINIATURA = (240, 240)
FORMATOS_PIL = {"JPEG": "image/jpeg", "PNG": "image/png"}


def _carpeta():
    return current_app.config["UPLOAD_FOLDER"]


def validar_fotos(archivos):
    """Revisa cantidad, tipo y tamaño. Devuelve [(bytes, mime, nombre)] sin guardar nada."""
    archivos = [a for a in archivos if a and a.filename]
    maximo = current_app.config["MAX_FOTOS"]
    max_bytes = current_app.config["MAX_MB_FOTO"] * 1024 * 1024
    permitidos = current_app.config["TIPOS_IMAGEN"]

    if len(archivos) > maximo:
        raise ErrorNegocio(f"Solo puedes adjuntar hasta {maximo} fotos.", campos={"fotos": f"Máximo {maximo} fotos."})

    validas = []
    for archivo in archivos:
        datos = archivo.read()
        nombre = os.path.basename(archivo.filename)[:200]
        if archivo.mimetype not in permitidos:
            raise ErrorNegocio(f'"{nombre}" no es una imagen JPG o PNG.', campos={"fotos": "Solo imágenes JPG o PNG."})
        if len(datos) > max_bytes:
            raise ErrorNegocio(f'"{nombre}" pesa más de {current_app.config["MAX_MB_FOTO"]} MB.',
                               campos={"fotos": "Cada foto debe pesar menos de 5 MB."})
        # Confirma que el contenido realmente es una imagen (no solo la extensión)
        try:
            with Image.open(BytesIO(datos)) as img:
                formato = img.format
                img.verify()
        except Exception:
            raise ErrorNegocio(f'"{nombre}" está dañada o no es una imagen.', campos={"fotos": "Archivo de imagen no válido."})
        if formato not in FORMATOS_PIL:
            raise ErrorNegocio(f'"{nombre}" no es una imagen JPG o PNG.', campos={"fotos": "Solo imágenes JPG o PNG."})
        validas.append((datos, FORMATOS_PIL[formato], nombre))
    return validas


def guardar_fotos(validas):
    """Guarda las imágenes ya validadas y crea su miniatura. Devuelve objetos TicketFoto."""
    os.makedirs(_carpeta(), exist_ok=True)
    fotos = []
    for datos, mime, nombre in validas:
        base = uuid.uuid4().hex
        archivo = f"{base}.{current_app.config['TIPOS_IMAGEN'][mime]}"
        miniatura = f"{base}_min.jpg"
        with open(os.path.join(_carpeta(), archivo), "wb") as f:
            f.write(datos)
        with Image.open(BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail(TAM_MINIATURA)
            img.convert("RGB").save(os.path.join(_carpeta(), miniatura), "JPEG", quality=82)
        fotos.append(TicketFoto(archivo=archivo, miniatura=miniatura, nombre_original=nombre, mime=mime))
    return fotos


def eliminar_archivos(fotos):
    for foto in fotos:
        for nombre in (foto.archivo, foto.miniatura):
            try:
                os.remove(os.path.join(_carpeta(), nombre))
            except OSError:
                pass


def imagen_de_ejemplo(texto, color):
    """Crea una imagen simple para los datos de prueba."""
    img = Image.new("RGB", (960, 640), color)
    dibujo = ImageDraw.Draw(img)
    dibujo.rectangle((380, 220, 580, 380), outline="#3F4C8C", width=8)
    dibujo.ellipse((420, 250, 460, 290), outline="#3F4C8C", width=6)
    dibujo.line((390, 370, 470, 300, 520, 340, 570, 290), fill="#3F4C8C", width=8)
    dibujo.text((40, 590), texto, fill="#3F4C8C")
    salida = BytesIO()
    img.save(salida, "JPEG", quality=85)
    return salida.getvalue()
