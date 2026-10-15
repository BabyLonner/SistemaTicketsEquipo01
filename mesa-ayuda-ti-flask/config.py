import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _bool(nombre, defecto="0"):
    return os.getenv(nombre, defecto) == "1"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-cambia-esta-clave")

    # Base de datos: SQLite si no defines DATABASE_URL
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///" + os.path.join(BASE_DIR, "instance", "mesa_ayuda.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT: la web lo guarda en una cookie HttpOnly; la API lo recibe en el header Authorization
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-cambia-esta-clave-jwt")
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_TOKEN_RECORDAR = timedelta(days=7)
    JWT_COOKIE_SECURE = _bool("COOKIE_SECURE")
    JWT_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_CHECK_FORM = True  # los formularios envían el campo csrf_token

    # Fotos de evidencia
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    MAX_FOTOS = 3
    MAX_MB_FOTO = 5
    TIPOS_IMAGEN = {"image/jpeg": "jpg", "image/png": "png"}

    CORREO_SOPORTE = os.getenv("CORREO_SOPORTE", "soporte@empresa.pe")
    ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Lima")
    MOSTRAR_CUENTAS_DEMO = _bool("MOSTRAR_CUENTAS_DEMO", "1")
    TICKETS_POR_PAGINA = 10
