"""MÓDULO 7 — Genera el par de llaves VAPID para las alertas Web Push.

Ejecútalo UNA sola vez y copia las dos líneas que imprime en el archivo .env
(en tu PC y en PythonAnywhere usa el MISMO par):
    python generar_vapid.py
Si cambias las llaves, cada usuario debe volver a pulsar "Activar Alertas Push".
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


privada = ec.generate_private_key(ec.SECP256R1())
privada_bytes = privada.private_numbers().private_value.to_bytes(32, "big")
publica_bytes = privada.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print("# Copia estas dos líneas en tu .env")
print(f"VAPID_PUBLIC_KEY={b64url(publica_bytes)}")
print(f"VAPID_PRIVATE_KEY={b64url(privada_bytes)}")
