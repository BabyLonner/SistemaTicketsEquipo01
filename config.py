"""Configuración general. Los valores se leen del archivo .env (ver .env.example)."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Ruta absoluta: en PythonAnywhere el WSGI no arranca desde la carpeta del proyecto
load_dotenv(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY") or "cambia-esta-clave-en-produccion"
JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)
JWT_HORAS = int(os.getenv("JWT_HORAS", "8"))            # sesión normal
JWT_DIAS_RECORDAR = int(os.getenv("JWT_DIAS_RECORDAR", "7"))  # "Mantener la sesión iniciada"
COOKIE_TOKEN = "mesa_token"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "mesa_ayuda_ti")

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 3 fotos x 5 MB + formulario

CORREO_SOPORTE = os.getenv("CORREO_SOPORTE", "soporte@mesadeayuda.com.pe")

# Módulo 8: dirección pública del sistema (el QR del PDF apunta a URL_BASE/verificar/<codigo>)
URL_BASE = os.getenv("URL_BASE", "http://127.0.0.1:5000").rstrip("/")
VERSION = "2.1.0"
