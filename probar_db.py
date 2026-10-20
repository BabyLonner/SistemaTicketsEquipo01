from db import obtener_conexion

try:
    conexion = obtener_conexion()

    with conexion.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM empresas")
        resultado = cursor.fetchone()

    print("¡Conexión exitosa!")
    print("Empresas registradas:", resultado["total"])

except Exception as error:
    print("Error de conexión:", error)

finally:
    if "conexion" in locals() and conexion.open:
        conexion.close()