"""Comandos de consola:
    flask --app run seed          Borra todo y carga datos de prueba
    flask --app run crear-admin   Crea un administrador con tus datos
"""
from datetime import timedelta

import click

from .archivos import eliminar_archivos, guardar_fotos, imagen_de_ejemplo
from .extensions import db
from .models import Notificacion, Ticket, TicketFoto, TicketHistorial, Usuario
from .sla import ahora

CLAVE_DEMO = "demo1234"


def registrar_comandos(app):
    @app.cli.command("seed")
    def seed():
        """Borra la base de datos y carga usuarios, tickets y notificaciones de ejemplo."""
        eliminar_archivos(TicketFoto.query.all())
        db.drop_all()
        db.create_all()
        _cargar_demo()
        click.echo(f"Datos de prueba listos. Todas las cuentas usan la contraseña: {CLAVE_DEMO}")

    @app.cli.command("crear-admin")
    @click.option("--nombre", prompt="Nombre completo")
    @click.option("--correo", prompt="Correo")
    @click.option("--empresa", prompt="Empresa", default="Grupo M&M")
    @click.password_option("--clave", prompt="Contraseña (mínimo 8 caracteres)")
    def crear_admin(nombre, correo, empresa, clave):
        """Crea un usuario administrador."""
        from .errores import ErrorNegocio
        from .servicios import crear_usuario
        try:
            u = crear_usuario({"nombre": nombre, "correo": correo, "password": clave, "rol": "Administrador",
                               "empresa": empresa, "area": "Administración"})
        except ErrorNegocio as e:
            raise click.ClickException("; ".join(e.campos.values()) or e.mensaje)
        click.echo(f"Administrador creado: {u.correo}")


def _cargar_demo():
    ahora_ = ahora()
    hace = lambda **kw: ahora_ - timedelta(**kw)  # noqa: E731

    datos_usuarios = [
        ("Ana Díaz", "ana.diaz@empresa.pe", "Administrador", "Grupo M&M", "Administración", True),
        ("Luis Ramos", "luis.ramos@empresa.pe", "Técnico", "Grupo M&M", "Operaciones", True),
        ("Carla Mendoza", "carla.mendoza@empresa.pe", "Técnico", "EPSEL", "Operaciones", True),
        ("Pedro Salazar", "pedro.salazar@empresa.pe", "Técnico", "Atlántica", "Operaciones", True),
        ("Jorge Paredes", "jorge.paredes@empresa.pe", "Solicitante", "Agrofutura", "Logística", True),
        ("Rosa Villanueva", "rosa.villanueva@empresa.pe", "Solicitante", "Angel Divino Bus", "Administración", True),
        ("Miguel Torres", "miguel.torres@empresa.pe", "Solicitante", "Robotic Air Systems", "Comercial", False),
        ("Lucía Campos", "lucia.campos@empresa.pe", "Solicitante", "Atlántica", "Comercial", True),
    ]
    u = {}
    for nombre, correo, rol, empresa, area, activo in datos_usuarios:
        usuario = Usuario(nombre=nombre, correo=correo, rol=rol, empresa=empresa, area=area, activo=activo,
                          created_at=hace(days=40))
        usuario.set_password(CLAVE_DEMO)
        db.session.add(usuario)
        u[nombre.split()[0].lower()] = usuario
    db.session.flush()

    colores = ["#E8E3DA", "#D9DEF5", "#CFEBDD", "#F7EDB8"]

    def ticket(asunto, descripcion, categoria, prioridad, estado, solicitante, tecnico, creado, cierre=None, fotos=()):
        t = Ticket(asunto=asunto, descripcion=descripcion, categoria=categoria, prioridad=prioridad, estado=estado,
                   empresa=solicitante.empresa, solicitante_id=solicitante.id,
                   tecnico_id=tecnico.id if tecnico else None, created_at=creado, updated_at=creado, cerrado_at=cierre)
        db.session.add(t)
        db.session.flush()
        if fotos:
            validas = [(imagen_de_ejemplo(n, colores[i % 4]), "image/jpeg", n) for i, n in enumerate(fotos)]
            t.fotos = guardar_fotos(validas)
        n = len(fotos)
        texto = "Ticket registrado." if not n else ("Se adjuntó 1 foto de evidencia." if n == 1 else f"Se adjuntaron {n} fotos de evidencia.")
        historial(t, solicitante, "creado", texto, creado)
        return t

    def historial(t, autor, tipo, texto, fecha, anterior=None, nuevo=None):
        db.session.add(TicketHistorial(ticket_id=t.id, usuario_id=autor.id, tipo=tipo, texto=texto, created_at=fecha,
                                       estado_anterior=anterior, estado_nuevo=nuevo))

    def notificacion(usuario, tipo, t, mensaje, fecha, leido=False):
        db.session.add(Notificacion(usuario_id=usuario.id, tipo=tipo, referencia_ticket=t.id, mensaje=mensaje,
                                    created_at=fecha, leido=leido))

    ana, luis, carla = u["ana"], u["luis"], u["carla"]
    jorge, rosa, miguel, lucia = u["jorge"], u["rosa"], u["miguel"], u["lucía"]

    t1 = ticket("Servidor de facturación caído",
                'Desde las 8:00 a. m. no se pueden emitir boletas ni facturas en las tres oficinas de venta de pasajes. '
                'El sistema muestra "No se puede conectar con el servidor".',
                "Software", "Alta", "En proceso", rosa, luis, hace(minutes=280),
                fotos=["error_servidor.jpg", "pantalla_caja.jpg", "rack_servidores.jpg"])
    historial(t1, ana, "asignado", "Ticket asignado a Luis Ramos", hace(minutes=240))
    historial(t1, luis, "estado", "Revisando los registros del servidor. El servicio se detuvo después de la actualización de anoche.",
              hace(minutes=190), "Abierto", "En proceso")

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
    historial(t5, carla, "estado", "Reconfigurando la cuenta de correo en el equipo móvil.", hace(hours=22), "Abierto", "En proceso")

    t6 = ticket("Alta de usuario en ERP", "Necesitamos crear el acceso al ERP para la nueva asistente comercial.",
                "Accesos y cuentas", "Baja", "Abierto", lucia, luis, hace(minutes=830))
    historial(t6, ana, "asignado", "Ticket asignado a Luis Ramos", hace(minutes=800))

    t7 = ticket("Monitor con líneas en pantalla",
                "El monitor de la oficina de logística muestra líneas horizontales que no dejan leer.",
                "Hardware", "Media", "Resuelto", jorge, carla, hace(hours=30), cierre=hace(hours=26), fotos=["monitor.jpg"])
    historial(t7, ana, "asignado", "Ticket asignado a Carla Mendoza", hace(hours=29))
    historial(t7, carla, "estado", "Revisando el cable de video y la tarjeta gráfica.", hace(hours=28), "Abierto", "En proceso")
    historial(t7, carla, "estado", "Se reemplazó el cable HDMI. El monitor funciona correctamente.", hace(hours=26), "En proceso", "Resuelto")

    t8 = ticket("Cambio de contraseña de correo", "Olvidé la contraseña de mi correo y no puedo restablecerla.",
                "Accesos y cuentas", "Baja", "Cerrado", rosa, luis, hace(days=3), cierre=hace(days=3) + timedelta(hours=10))
    historial(t8, ana, "asignado", "Ticket asignado a Luis Ramos", hace(days=3) + timedelta(hours=1))
    historial(t8, luis, "estado", "Se restableció la contraseña y se envió la temporal por mensaje.",
              hace(days=3) + timedelta(hours=10), "Abierto", "Resuelto")
    historial(t8, luis, "estado", "La usuaria confirmó que ya puede ingresar.", hace(days=2), "Resuelto", "Cerrado")

    notificacion(ana, "nuevo", t4, f"Nuevo ticket {t4.codigo} por asignar", hace(hours=5))
    notificacion(luis, "asignacion", t1, f"Se te asignó el ticket {t1.codigo}", hace(minutes=240))
    notificacion(luis, "asignacion", t6, f"Se te asignó el ticket {t6.codigo}", hace(minutes=800), leido=True)
    notificacion(luis, "asignacion", t3, f"Se te asignó el ticket {t3.codigo}", hace(hours=20), leido=True)
    notificacion(carla, "asignacion", t2, f"Se te asignó el ticket {t2.codigo}", hace(minutes=170))
    notificacion(rosa, "estado", t1, f"{t1.codigo} cambió a En proceso", hace(minutes=190))
    notificacion(jorge, "estado", t2, f"{t2.codigo} cambió a En proceso", hace(minutes=150))
    notificacion(jorge, "estado", t7, f"{t7.codigo} cambió a Resuelto", hace(hours=26), leido=True)
    notificacion(lucia, "comentario", t3, f"Nuevo comentario en {t3.codigo}", hace(hours=6))

    db.session.commit()
