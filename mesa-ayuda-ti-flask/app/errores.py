class ErrorNegocio(Exception):
    """Error de validación o de una regla del sistema, con el código HTTP a devolver."""

    def __init__(self, mensaje, status=400, campos=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.campos = campos or {}
