import pymysql.cursors

# Datos de conexión a MySQL (XAMPP usa root sin contraseña)
BD_HOST = "localhost"
BD_USUARIO = "root"
BD_PASSWORD = ""
BD_NOMBRE = "mesa_ayuda_ti"


def obtenerconexion():
    try:
        connection = pymysql.connect(host=BD_HOST,
                                     user=BD_USUARIO,
                                     password=BD_PASSWORD,
                                     database=BD_NOMBRE,
                                     charset="utf8mb4",
                                     cursorclass=pymysql.cursors.DictCursor)
        return connection
    except Exception as e:
        raise e
