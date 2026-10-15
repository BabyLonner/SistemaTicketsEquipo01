"""Carga datos de prueba en la base mesa_ayuda_ti.

Antes ejecuta sql/mesa_ayuda_ti.sql en phpMyAdmin.
Luego:  python cargar_datos.py

OJO: borra todos los usuarios, tickets y notificaciones que haya.
"""
from datetime import timedelta

from bd import obtenerconexion
from controlador_usuarios import encriptar_password
from utilidades import CARPETA_UPLOADS, ahora, guardar_fotos, imagen_de_ejemplo

import os

PASSWORD_DEMO = "demo1234"
COLORES = ["#E8E3DA", "#D9DEF5", "#CFEBDD", "#F7EDB8"]


def limpiar(cursor):
    for tabla in ("notificaciones", "ticket_historial", "ticket_fotos", "tickets", "tokens_revocados", "users"):
        cursor.execute("DELETE FROM " + tabla)
        cursor.execute("ALTER TABLE " + tabla + " AUTO_INCREMENT = 1")
    for nombre in os.listdir(CARPETA_UPLOADS):
        if nombre != ".gitkeep":
            os.remove(os.path.join(CARPETA_UPLOADS, nombre))


def cargar():
    momento = ahora()

    def hace(**tiempo):
        return momento - timedelta(**tiempo)

    conexion = obtenerconexion()
    with conexion:
        with conexion.cursor() as cursor:
            limpiar(cursor)

            # ---------------- Usuarios ----------------
            usuarios = [
                ("Ana Díaz", "ana.diaz@empresa.pe", "Administrador", "Grupo M&M", "Administración", 1),
                ("Luis Ramos", "luis.ramos@empresa.pe", "Técnico", "Grupo M&M", "Operaciones", 1),
                ("Carla Mendoza", "carla.mendoza@empresa.pe", "Técnico", "EPSEL", "Operaciones", 1),
                ("Pedro Salazar", "pedro.salazar@empresa.pe", "Técnico", "Atlántica", "Operaciones", 1),
                ("Jorge Paredes", "jorge.paredes@empresa.pe", "Solicitante", "Agrofutura", "Logística", 1),
                ("Rosa Villanueva", "rosa.villanueva@empresa.pe", "Solicitante", "Angel Divino Bus", "Administración", 1),
                ("Miguel Torres", "miguel.torres@empresa.pe", "Solicitante", "Robotic Air Systems", "Comercial", 0),
                ("Lucía Campos", "lucia.campos@empresa.pe", "Solicitante", "Atlántica", "Comercial", 1),
            ]
            hash_demo = encriptar_password(PASSWORD_DEMO)
            ids = {}
            for nombre, email, rol, empresa, area, activo in usuarios:
                cursor.execute("INSERT INTO users (nombre, email, password, rol, empresa, area, activo, created_at) "
                               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                               (nombre, email, hash_demo, rol, empresa, area, activo, hace(days=40)))
                ids[nombre.split()[0]] = {"id": cursor.lastrowid, "empresa": empresa}

            ana, luis, carla = ids["Ana"]["id"], ids["Luis"]["id"], ids["Carla"]["id"]
            jorge, rosa, miguel, lucia = ids["Jorge"], ids["Rosa"], ids["Miguel"], ids["Lucía"]

            # ---------------- Tickets ----------------
            def ticket(asunto, descripcion, categoria, prioridad, estado, solicitante, tecnico, creado, cierre=None, fotos=()):
                cursor.execute("INSERT INTO tickets (asunto, descripcion, categoria, prioridad, estado, empresa, "
                               "solicitante_id, tecnico_id, created_at, updated_at, cerrado_at) "
                               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                               (asunto, descripcion, categoria, prioridad, estado, solicitante["empresa"],
                                solicitante["id"], tecnico, creado, creado, cierre))
                ticket_id = cursor.lastrowid
                validas = [(imagen_de_ejemplo(n, COLORES[i % 4]), "image/jpeg", n) for i, n in enumerate(fotos)]
                for f in guardar_fotos(validas):
                    cursor.execute("INSERT INTO ticket_fotos (ticket_id, archivo, miniatura, nombre_original, mime, created_at) "
                                   "VALUES (%s, %s, %s, %s, %s, %s)",
                                   (ticket_id, f["archivo"], f["miniatura"], f["nombre_original"], f["mime"], creado))
                n = len(fotos)
                texto = "Ticket registrado." if n == 0 else ("Se adjuntó 1 foto de evidencia." if n == 1
                                                             else "Se adjuntaron " + str(n) + " fotos de evidencia.")
                historial(ticket_id, solicitante["id"], "creado", texto, creado)
                return ticket_id

            def historial(ticket_id, autor, tipo, texto, fecha, anterior=None, nuevo=None):
                cursor.execute("INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, "
                               "texto, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                               (ticket_id, autor, tipo, anterior, nuevo, texto, fecha))

            def notificacion(usuario_id, tipo, ticket_id, mensaje, fecha, leido=0):
                cursor.execute("INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, mensaje, leido, created_at) "
                               "VALUES (%s, %s, %s, %s, %s, %s)", (usuario_id, tipo, ticket_id, mensaje, leido, fecha))

            t1 = ticket("Servidor de facturación caído",
                        'Desde las 8:00 a. m. no se pueden emitir boletas ni facturas en las tres oficinas de venta de '
                        'pasajes. El sistema muestra "No se puede conectar con el servidor".',
                        "Software", "Alta", "En proceso", rosa, luis, hace(minutes=280),
                        fotos=["error_servidor.jpg", "pantalla_caja.jpg", "rack_servidores.jpg"])
            historial(t1, ana, "asignado", "Ticket asignado a Luis Ramos", hace(minutes=240))
            historial(t1, luis, "estado", "Revisando los registros del servidor. El servicio se detuvo después de la "
                                          "actualización de anoche.", hace(minutes=190), "Abierto", "En proceso")

            t2 = ticket("VPN no conecta desde almacén",
                        "Desde el almacén la VPN se desconecta a los pocos segundos y no permite entrar al sistema de inventario.",
                        "Red e internet", "Alta", "En proceso", jorge, carla, hace(minutes=190), fotos=["vpn_error.png"])
            historial(t2, ana, "asignado", "Ticket asignado a Carla Mendoza", hace(minutes=170))
            historial(t2, carla, "estado", "Verificando la configuración del cliente VPN en el equipo del almacén.",
                      hace(minutes=150), "Abierto", "En proceso")

            t3 = ticket("Laptop no enciende",
                        "La laptop del área comercial no enciende. El cargador tiene la luz prendida, pero la pantalla se queda en negro.",
                        "Hardware", "Media", "Abierto", lucia, luis, hace(hours=21), fotos=["laptop.jpg"])
            historial(t3, ana, "asignado", "Ticket asignado a Luis Ramos", hace(hours=20))
            historial(t3, luis, "comentario", "Pasaré por el área a revisar el equipo esta tarde.", hace(hours=6))

            t4 = ticket("Impresora de despacho sin tóner",
                        "La impresora de despacho imprime las guías casi en blanco. Parece que se terminó el tóner.",
                        "Impresoras", "Media", "Abierto", rosa, None, hace(hours=5), fotos=["impresora_01.jpg"])

            t5 = ticket("Correo no sincroniza en el celular",
                        "El correo corporativo dejó de llegar al celular desde ayer. En la computadora sí llega.",
                        "Correo", "Baja", "En proceso", miguel, carla, hace(hours=24))
            historial(t5, ana, "asignado", "Ticket asignado a Carla Mendoza", hace(hours=23))
            historial(t5, carla, "estado", "Reconfigurando la cuenta de correo en el equipo móvil.", hace(hours=22),
                      "Abierto", "En proceso")

            t6 = ticket("Alta de usuario en ERP", "Necesitamos crear el acceso al ERP para la nueva asistente comercial.",
                        "Accesos y cuentas", "Baja", "Abierto", lucia, luis, hace(minutes=830))
            historial(t6, ana, "asignado", "Ticket asignado a Luis Ramos", hace(minutes=800))

            t7 = ticket("Monitor con líneas en pantalla",
                        "El monitor de la oficina de logística muestra líneas horizontales que no dejan leer.",
                        "Hardware", "Media", "Resuelto", jorge, carla, hace(hours=30), cierre=hace(hours=26), fotos=["monitor.jpg"])
            historial(t7, ana, "asignado", "Ticket asignado a Carla Mendoza", hace(hours=29))
            historial(t7, carla, "estado", "Revisando el cable de video y la tarjeta gráfica.", hace(hours=28),
                      "Abierto", "En proceso")
            historial(t7, carla, "estado", "Se reemplazó el cable HDMI. El monitor funciona correctamente.", hace(hours=26),
                      "En proceso", "Resuelto")

            t8 = ticket("Cambio de contraseña de correo", "Olvidé la contraseña de mi correo y no puedo restablecerla.",
                        "Accesos y cuentas", "Baja", "Cerrado", rosa, luis, hace(days=3), cierre=hace(days=3) + timedelta(hours=10))
            historial(t8, ana, "asignado", "Ticket asignado a Luis Ramos", hace(days=3) + timedelta(hours=1))
            historial(t8, luis, "estado", "Se restableció la contraseña y se envió la temporal por mensaje.",
                      hace(days=3) + timedelta(hours=10), "Abierto", "Resuelto")
            historial(t8, luis, "estado", "La usuaria confirmó que ya puede ingresar.", hace(days=2), "Resuelto", "Cerrado")

            # ---------------- Notificaciones ----------------
            notificacion(ana, "nuevo", t4, "Nuevo ticket TK-0004 por asignar", hace(hours=5))
            notificacion(luis, "asignacion", t1, "Se te asignó el ticket TK-0001", hace(minutes=240))
            notificacion(luis, "asignacion", t6, "Se te asignó el ticket TK-0006", hace(minutes=800), 1)
            notificacion(luis, "asignacion", t3, "Se te asignó el ticket TK-0003", hace(hours=20), 1)
            notificacion(carla, "asignacion", t2, "Se te asignó el ticket TK-0002", hace(minutes=170))
            notificacion(rosa["id"], "estado", t1, "TK-0001 cambió a En proceso", hace(minutes=190))
            notificacion(jorge["id"], "estado", t2, "TK-0002 cambió a En proceso", hace(minutes=150))
            notificacion(jorge["id"], "estado", t7, "TK-0007 cambió a Resuelto", hace(hours=26), 1)
            notificacion(lucia["id"], "comentario", t3, "Nuevo comentario en TK-0003", hace(hours=6))

        conexion.commit()


if __name__ == "__main__":
    try:
        cargar()
        print("Datos de prueba cargados. Todas las cuentas usan la contraseña: " + PASSWORD_DEMO)
    except Exception as e:
        print("Error: " + repr(e))
        print("Revisa que MySQL esté encendido y que hayas ejecutado sql/mesa_ayuda_ti.sql")
