"""
MÓDULO 8 — Verificación de autenticidad de los reportes PDF.

Cómo funciona:
  1. Al generar el PDF (reportes.py) se crea un código aleatorio que va dentro
     del código QR:  URL_BASE/verificar/<codigo>
  2. Con el PDF ya terminado se calcula su huella SHA-256 y se guarda en la
     tabla reportes_generados junto al código.
  3. Quien recibe el PDF escanea el QR, sube el archivo y el servidor vuelve a
     calcular el SHA-256: si cambió un solo byte, la huella es otra.

El hash no se imprime dentro del PDF: hacerlo cambiaría el propio archivo y su hash.

  GET  /verificar/<codigo>   datos del reporte (página pública, sin login)
  POST /verificar/<codigo>   compara el PDF subido con la huella guardada
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime

from flask import Blueprint, render_template, request

import config
from db import conexion, consultar

verificacion_bp = Blueprint("verificacion", __name__)

FORMATO_CODIGO = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
MAX_PDF = 10 * 1024 * 1024


def nuevo_codigo():
    """Código impredecible (128 bits): nadie puede adivinar el de otro reporte."""
    return secrets.token_urlsafe(16)


def url_verificacion(codigo):
    return f"{config.URL_BASE}/verificar/{codigo}"


def huella_sha256(datos):
    return hashlib.sha256(datos).hexdigest()


def _fecha_o_nula(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def registrar_reporte(codigo, empresa_id, pdf, desde, hasta, filtros, total, usuario_id):
    """Guarda la huella del PDF recién generado."""
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO reportes_generados
                 (codigo, empresa_id, periodo_desde, periodo_hasta, filtros, total_tickets, hash_sha256, generado_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (codigo, empresa_id, _fecha_o_nula(desde), _fecha_o_nula(hasta), filtros[:500], total,
             huella_sha256(pdf), usuario_id),
        )
    con.commit()


def _buscar(codigo):
    if not FORMATO_CODIGO.match(codigo):
        return None
    return consultar(
        """SELECT r.codigo, r.periodo_desde, r.periodo_hasta, r.filtros, r.total_tickets, r.hash_sha256,
                  r.created_at, e.nombre AS empresa, e.logo_url, e.color_primario,
                  COALESCE(u.nombre, 'Envío automático') AS generado_por
             FROM reportes_generados r
             JOIN empresas e    ON e.id = r.empresa_id
             LEFT JOIN users u  ON u.id = r.generado_por
            WHERE r.codigo = %s""",
        (codigo,), uno=True,
    )


@verificacion_bp.route("/verificar/<codigo>", methods=["GET", "POST"])
def verificar(codigo):
    reporte = _buscar(codigo)
    if not reporte:
        return render_template("verificar.html", reporte=None, codigo=codigo), 404

    resultado, error, huella_subida = None, None, None
    if request.method == "POST":
        archivo = request.files.get("pdf")
        datos = archivo.read(MAX_PDF + 1) if archivo else b""
        if not datos:
            error = "Selecciona el archivo PDF que quieres verificar."
        elif len(datos) > MAX_PDF:
            error = "El archivo es demasiado grande (máximo 10 MB)."
        elif not datos.startswith(b"%PDF"):
            error = "El archivo no es un PDF."
        else:
            huella_subida = huella_sha256(datos)
            # compare_digest compara en tiempo constante (no revela cuántos caracteres coinciden)
            resultado = "autentico" if hmac.compare_digest(huella_subida, reporte["hash_sha256"]) else "alterado"

    return render_template("verificar.html", reporte=reporte, codigo=codigo, resultado=resultado,
                           error=error, huella_subida=huella_subida)
