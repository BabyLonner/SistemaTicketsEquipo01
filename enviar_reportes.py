"""
MÓDULO 8 — Envío semanal automático. Lo ejecuta una tarea programada (cron), en un proceso
separado de la web: por eso el envío no bloquea la aplicación.

    python enviar_reportes.py            # envío normal (ver abajo)
    python enviar_reportes.py --forzar   # envía hoy, aunque ya se haya enviado (para probar)

La cuenta gratuita de PythonAnywhere solo permite tareas DIARIAS, así que el script corre todos
los días y revisa la programación de cada empresa (Configuración → Reporte semanal por correo):
  * Día programado: envía los 7 días anteriores a los correos marcados con "Envío semanal".
  * Otros días: solo reintenta el último envío si falló.
  * Envío desactivado: no hace nada, ni siquiera con --forzar.
"""
import sys

import sys

from envios import procesar_envios_programados
from run import app
from utils import ahora


def main():
    forzar = "--forzar" in sys.argv
    print(f"{ahora():%d/%m/%Y %H:%M} - Revisando la programación de cada empresa")
    with app.app_context():  # db.conexion() guarda la conexión en flask.g
        resultados, errores = procesar_envios_programados(ahora().date(), forzar)
    for linea in resultados:
        print(f"  {linea}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())