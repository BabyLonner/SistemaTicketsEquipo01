"""Prueba rápida de conexión:  python probar_db.py"""
from db import obtener_conexion

try:
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM empresas")
        empresas = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        usuarios = cursor.fetchone()["total"]
        cursor.execute("SELECT NOW() AS ahora")
        ahora = cursor.fetchone()["ahora"]
    conexion.close()
    print("¡Conexión exitosa!")
    print("Empresas:", empresas, "| Usuarios:", usuarios, "| Hora del servidor (Perú):", ahora)
except Exception as error:  # noqa: BLE001
    print("Error de conexión:", error)
