"""MÓDULO 8 — Agrega a una base de datos EXISTENTE lo necesario para el reporte verificable y el envío por correo.

NO borra datos. Se puede ejecutar varias veces sin problema (revisa antes de crear).
    Local:          python migrar_modulo8.py
    PythonAnywhere: python3.13 migrar_modulo8.py

Hace dos cosas:
<<<<<<< HEAD
  1. Tablas reportes_generados, reporte_destinatarios, reporte_envios y reporte_programacion
     (ver database/migracion_modulo8.sql)
=======
  1. Tablas reportes_generados, reporte_destinatarios, reporte_envios y reporte_programacion (ver database/migracion_modulo8.sql)
>>>>>>> 4aaa3aec5c2cc6b98e5a09a9610317a37e618037
  2. Columna reporte_destinatarios.semanal: los correos que ya existían quedan con envío semanal
"""
import os

from db import obtener_conexion
from inicializar_bd import sentencias

RUTA_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "migracion_modulo8.sql")


def main():
    with open(RUTA_SQL, encoding="utf-8") as f:
        texto = f.read()
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            for sql in sentencias(texto):
                cur.execute(sql)
            cur.execute(
                """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reporte_destinatarios'
                      AND COLUMN_NAME = 'semanal'"""
            )
            if cur.fetchone()["n"]:
                print("  ya existe reporte_destinatarios.semanal")
            else:
                cur.execute("ALTER TABLE reporte_destinatarios ADD COLUMN semanal TINYINT(1) NOT NULL DEFAULT 1 AFTER correo")
                print("  agregada reporte_destinatarios.semanal")
        con.commit()
    finally:
        con.close()
    print("Listo: Módulo 8 aplicado (los datos existentes no se tocaron).")


if __name__ == "__main__":
    main()
