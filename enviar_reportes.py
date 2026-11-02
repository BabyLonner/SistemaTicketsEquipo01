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

from db import consultar
from envios import (
    destinatarios_semanales, enviar_reporte_empresa, fallo_el_envio, periodo_de_envio, programacion_de,
    ultimo_dia_programado, ya_enviado,
)
from run import app
from utils import ahora


def main():
    forzar = "--forzar" in sys.argv
    hoy = ahora().date()
    errores = 0
    print(f"{ahora():%d/%m/%Y %H:%M} - Revisando la programación de cada empresa")
    with app.app_context():  # db.conexion() guarda la conexión en flask.g
        for empresa in consultar("SELECT * FROM empresas WHERE activo = 1 ORDER BY id"):
            nombre = empresa["nombre"]
            programacion = programacion_de(empresa["id"])
            if not programacion["activo"]:
                print(f"  {nombre}: envío automático desactivado.")
                continue
            correos = destinatarios_semanales(empresa["id"])
            if not correos:
                print(f"  {nombre}: sin destinatarios con envío semanal.")
                continue
            fecha_envio = ultimo_dia_programado(programacion["dia_semana"], hoy)
            desde, hasta = periodo_de_envio(fecha_envio)
            if not forzar:
                if ya_enviado(empresa["id"], desde):
                    print(f"  {nombre}: ya se envió el reporte del {desde:%d/%m} al {hasta:%d/%m}.")
                    continue
                if fecha_envio != hoy and not fallo_el_envio(empresa["id"], desde):
                    print(f"  {nombre}: hoy no le toca y no hay envíos pendientes.")
                    continue
            try:
                ok, mensaje = enviar_reporte_empresa(empresa, desde, hasta, "automatico", correos)
            except Exception as e:  # noqa: BLE001  una empresa con problemas no detiene a las demás
                ok, mensaje = False, f"Error inesperado: {e}"
            print(f"  {nombre} ({desde:%d/%m} al {hasta:%d/%m}): {'OK' if ok else 'NO ENVIADO'} - {mensaje}")
            errores += 0 if ok else 1
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
