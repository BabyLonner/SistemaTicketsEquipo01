"""Conexión a MySQL con PyMySQL (igual que en clase, pero con datos del .env)."""
import pymysql
import pymysql.cursors

import config


def obtener_conexion():
    """Abre una conexión nueva. Cada conexión trabaja en hora de Perú (UTC-5),
    así NOW() devuelve lo mismo en XAMPP y en PythonAnywhere (que está en UTC)."""
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        init_command="SET time_zone = '-05:00'",
        autocommit=False,
    )


# ---------------------------------------------------------------------
#  Una conexión por petición HTTP (se cierra sola al terminar, ver run.py)
# ---------------------------------------------------------------------
def conexion():
    from flask import g

    if "db" not in g:
        g.db = obtener_conexion()
    return g.db


def cerrar_conexion(_error=None):
    from flask import g

    con = g.pop("db", None)
    if con is not None:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def consultar(sql, params=None, uno=False):
    """SELECT rápido con la conexión de la petición."""
    with conexion().cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone() if uno else cur.fetchall()
