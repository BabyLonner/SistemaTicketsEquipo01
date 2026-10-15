"""Crea un administrador con tus datos (sin cargar datos de prueba).
Uso:  python crear_admin.py
"""
from getpass import getpass

import controlador_usuarios
from utilidades import EMPRESAS, ErrorNegocio

nombre = input("Nombre completo: ")
email = input("Correo: ")
print("Empresas: " + ", ".join(EMPRESAS))
empresa = input("Empresa: ")
password = getpass("Contraseña (mínimo 8 caracteres): ")

try:
    usuario = controlador_usuarios.crear({"nombre": nombre, "email": email, "password": password,
                                          "rol": "Administrador", "empresa": empresa, "area": "Administración"})
    print("Administrador creado: " + usuario["email"])
except ErrorNegocio as e:
    print("No se pudo crear: " + "; ".join(e.campos.values()))
