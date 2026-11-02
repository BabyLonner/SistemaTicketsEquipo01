"""
MÓDULO 8 — Envío de correo por SMTP (por defecto Gmail, puerto 587 con STARTTLS).

Pasos de la conversación con el servidor (smtplib los hace por nosotros):
  EHLO -> STARTTLS (cifra la conexión y comprueba el certificado) -> AUTH -> MAIL FROM -> RCPT TO -> DATA -> QUIT
El PDF viaja como adjunto MIME codificado en Base64 (EmailMessage lo arma).
"""
import smtplib
import ssl
from email.message import EmailMessage

import config


class ErrorCorreo(Exception):
    """Error con un mensaje claro para mostrar en pantalla y guardar en el historial."""


def smtp_configurado():
    return bool(config.SMTP_USER and config.SMTP_PASSWORD)


def enviar_correo(destinatarios, asunto, texto, adjunto=None, nombre_adjunto="reporte.pdf"):
    """Envía el correo. Devuelve los destinatarios rechazados ({} si todos fueron aceptados)."""
    if not smtp_configurado():
        raise ErrorCorreo("Falta configurar SMTP_USER y SMTP_PASSWORD en el archivo .env.")
    msg = EmailMessage()
    msg["From"] = config.SMTP_REMITENTE
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = asunto
    msg.set_content(texto)
    if adjunto:
        msg.add_attachment(adjunto, maintype="application", subtype="pdf", filename=nombre_adjunto)
    # El orden importa: SMTPException y SSLError también son OSError
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())   # sin contexto no se comprueba el certificado
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            return smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise ErrorCorreo(f"El servidor rechazó el usuario o la contraseña de aplicación (código {e.smtp_code}).") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise ErrorCorreo("El servidor rechazó todos los destinatarios.") from e
    except smtplib.SMTPException as e:
        raise ErrorCorreo(f"Error del servidor SMTP: {e}") from e
    except ssl.SSLError as e:
        raise ErrorCorreo(f"No se pudo establecer la conexión segura con {config.SMTP_HOST}: {e}") from e
    except OSError as e:
        raise ErrorCorreo(f"No se pudo conectar a {config.SMTP_HOST}:{config.SMTP_PORT} ({e}).") from e
