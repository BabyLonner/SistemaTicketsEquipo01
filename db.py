
import os

import pymysql
from dotenv import load_dotenv

load_dotenv()


def obtener_conexion():
    """Abre una conexión con la base de datos local."""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "admin"),       # Cambiado a 'root'
        password=os.getenv("DB_PASSWORD", "admin"),   # Contraseña vacía para XAMPP
        database=os.getenv("DB_NAME", "mesa_ayuda_ti"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )
