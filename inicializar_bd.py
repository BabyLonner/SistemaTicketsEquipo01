"""Crea todas las tablas y carga los datos de ejemplo ejecutando database/mesa_ayuda_ti.sql.

Úsalo en PythonAnywhere (consola Bash, dentro de la carpeta del proyecto):
    python inicializar_bd.py
⚠ Borra y vuelve a crear todas las tablas.
"""
import os
import re
import sys

from db import obtener_conexion

RUTA_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "mesa_ayuda_ti.sql")


def sentencias(texto):
    """Quita comentarios '--' y separa el script por ';' al final de línea."""
    lineas = [l for l in texto.splitlines() if not l.strip().startswith("--")]
    limpio = "\n".join(lineas)
    for bloque in re.split(r";\s*\n", limpio + "\n"):
        if bloque.strip():
            yield bloque.strip().rstrip(";")


def main():
    if "--si" not in sys.argv:
        resp = input("Esto BORRA y vuelve a crear todas las tablas. ¿Continuar? (s/n): ")
        if resp.strip().lower() != "s":
            print("Cancelado.")
            return
    with open(RUTA_SQL, encoding="utf-8") as f:
        texto = f.read()
    con = obtener_conexion()
    total = 0
    try:
        with con.cursor() as cur:
            for sql in sentencias(texto):
                cur.execute(sql)
                total += 1
        con.commit()
    finally:
        con.close()
    print(f"Listo: {total} sentencias ejecutadas. Usuario: superadmin@mesadeayuda.com.pe / Clave123")


if __name__ == "__main__":
    main()
