from datetime import timezone

from .extensions import bcrypt, db
from .sla import ahora, calcular


def iso(dt):
    """Fecha UTC en formato ISO 8601 con Z, para la API y el JavaScript."""
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


class Usuario(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    correo = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="Solicitante")
    empresa = db.Column(db.String(60), nullable=False)
    area = db.Column(db.String(60))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=ahora)

    def set_password(self, clave):
        self.password_hash = bcrypt.generate_password_hash(clave).decode("utf-8")

    def check_password(self, clave):
        return bcrypt.check_password_hash(self.password_hash, clave)

    @property
    def iniciales(self):
        return "".join(p[0] for p in self.nombre.split()[:2]).upper()

    @property
    def primer_nombre(self):
        return self.nombre.split()[0]

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "correo": self.correo, "rol": self.rol,
                "empresa": self.empresa, "area": self.area, "activo": self.activo,
                "created_at": iso(self.created_at)}


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    asunto = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(40), nullable=False, index=True)
    prioridad = db.Column(db.String(10), nullable=False, index=True)
    estado = db.Column(db.String(20), nullable=False, default="Abierto", index=True)
    empresa = db.Column(db.String(60), nullable=False, index=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=ahora, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)
    cerrado_at = db.Column(db.DateTime)

    solicitante = db.relationship("Usuario", foreign_keys=[solicitante_id])
    tecnico = db.relationship("Usuario", foreign_keys=[tecnico_id])
    fotos = db.relationship("TicketFoto", backref="ticket", cascade="all, delete-orphan", order_by="TicketFoto.id")
    historial = db.relationship("TicketHistorial", backref="ticket", cascade="all, delete-orphan",
                                order_by="TicketHistorial.created_at")
    notificaciones = db.relationship("Notificacion", backref="ticket", cascade="all, delete-orphan")

    @property
    def codigo(self):
        return f"TK-{self.id:04d}"

    @property
    def sla(self):
        """Campo calculado de urgencia."""
        return calcular(self.prioridad, self.created_at, self.cerrado_at)

    def to_dict(self, detalle=False):
        s = self.sla
        datos = {
            "id": self.id, "codigo": self.codigo, "asunto": self.asunto, "categoria": self.categoria,
            "prioridad": self.prioridad, "estado": self.estado, "empresa": self.empresa,
            "solicitante": {"id": self.solicitante.id, "nombre": self.solicitante.nombre},
            "tecnico": {"id": self.tecnico.id, "nombre": self.tecnico.nombre} if self.tecnico else None,
            "created_at": iso(self.created_at), "cerrado_at": iso(self.cerrado_at),
            "sla": {"nivel": s["nivel"], "texto": s["texto"], "horas_limite": s["horas_limite"],
                    "porcentaje_consumido": round(s["ratio"] * 100)},
            "total_fotos": len(self.fotos),
        }
        if detalle:
            datos["descripcion"] = self.descripcion
            datos["fotos"] = [f.to_dict() for f in self.fotos]
            datos["historial"] = [h.to_dict() for h in self.historial]
        return datos


class TicketFoto(db.Model):
    __tablename__ = "ticket_fotos"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    archivo = db.Column(db.String(80), nullable=False, unique=True)
    miniatura = db.Column(db.String(80), nullable=False, unique=True)
    nombre_original = db.Column(db.String(200), nullable=False)
    mime = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=ahora)

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre_original, "mime": self.mime,
                "url": f"/uploads/{self.archivo}", "miniatura": f"/uploads/{self.miniatura}"}


class TicketHistorial(db.Model):
    __tablename__ = "ticket_historial"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # creado, asignado, estado, comentario
    estado_anterior = db.Column(db.String(20))
    estado_nuevo = db.Column(db.String(20))
    texto = db.Column(db.Text, nullable=False)  # obligatorio
    created_at = db.Column(db.DateTime, nullable=False, default=ahora)

    usuario = db.relationship("Usuario")

    @property
    def titulo(self):
        if self.tipo == "estado":
            return f"Estado cambiado: {self.estado_anterior} → {self.estado_nuevo}"
        if self.tipo == "asignado":
            return self.texto
        if self.tipo == "comentario":
            return "Nuevo comentario"
        return "Ticket creado"

    @property
    def comentario(self):
        """Texto que se muestra debajo del título en la línea de tiempo."""
        return "" if self.tipo == "asignado" else self.texto

    def to_dict(self):
        return {"id": self.id, "tipo": self.tipo, "titulo": self.titulo, "texto": self.texto,
                "estado_anterior": self.estado_anterior, "estado_nuevo": self.estado_nuevo,
                "usuario": {"id": self.usuario.id, "nombre": self.usuario.nombre, "rol": self.usuario.rol},
                "created_at": iso(self.created_at)}


class Notificacion(db.Model):
    __tablename__ = "notificaciones"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)  # nuevo, asignacion, estado, comentario
    referencia_ticket = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False)
    mensaje = db.Column(db.String(200), nullable=False)
    leido = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=ahora)

    def to_dict(self):
        return {"id": self.id, "tipo": self.tipo, "mensaje": self.mensaje, "leido": self.leido,
                "referencia_ticket": self.referencia_ticket, "created_at": iso(self.created_at)}


class TokenRevocado(db.Model):
    """Tokens JWT invalidados al cerrar sesión."""
    __tablename__ = "tokens_revocados"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=ahora)
