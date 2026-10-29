"""
MÓDULO 1 (investigación) — Inicio de sesión con reconocimiento facial.

Cómo funciona
-------------
1. En el navegador, face-api.js (TensorFlow.js) detecta el rostro en la cámara y
   calcula su DESCRIPTOR FACIAL: un vector de 128 números que resume la forma del
   rostro (distancias y proporciones aprendidas por una red neuronal ResNet-34).
   La foto nunca sale del navegador.
2. Registro (Mi Perfil): se toman 3 capturas, el servidor comprueba que sean de la
   misma persona, guarda el PROMEDIO de los 3 descriptores en usuario_rostros y
   pide la contraseña actual para confirmar que es el dueño de la cuenta.
3. Login facial: el usuario escribe su correo y mira la cámara (1:1, se compara
   solo con el rostro de esa cuenta). El servidor calcula la DISTANCIA EUCLIDIANA
       d(a, b) = raíz( Σ (a_i − b_i)²  para i = 1..128 )
   entre el descriptor recibido y el guardado. Si d <= UMBRAL, es la misma persona.
4. Límite de intentos: 5 fallos en 15 minutos bloquean el login facial de esa cuenta
   (el login con contraseña sigue disponible). Además, máx. 20 intentos por IP.

Umbral: face-api.js recomienda 0.6. Usamos 0.45 (más estricto): con la cámara web, la misma
luz y el mismo fondo, dos personas distintas pueden quedar más cerca que en fotos distintas,
y con 0.5 llegó a entrar otra persona. Un umbral bajo reduce los falsos positivos a cambio
de que, con mala luz, a veces haya que intentarlo otra vez. Se cambia con UMBRAL_FACIAL en el .env.
"""
import json
import math
import os

from flask import Blueprint, g, jsonify, make_response, request, session, url_for

import config
from auth import (
    ROL_SUPER, clave_correcta, crear_token, llenar_sesion, login_requerido, registrar_acceso, verificar_cuenta,
)
from db import conexion, consultar
from vistas import V_USUARIOS_SESION

facial_bp = Blueprint("facial", __name__)

UMBRAL = float(os.getenv("UMBRAL_FACIAL", "0.45"))
UMBRAL_MISMA_PERSONA_REGISTRO = 0.45   # las 3 capturas del registro deben parecerse entre sí
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
MAX_INTENTOS_IP = 20
LARGO_DESCRIPTOR = 128
MUESTRAS_REGISTRO = 3


# ------------------------------------------------------------------ matemática
def distancia_euclidiana(a, b):
    """d = sqrt( sum((a_i - b_i)^2) ). 0 = idénticos; mientras más grande, más distintos."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def promedio(descriptores):
    return [sum(valores) / len(valores) for valores in zip(*descriptores)]


def validar_descriptor(valor):
    """Debe ser una lista de 128 números finitos (los de face-api.js están entre -1 y 1)."""
    if not isinstance(valor, list) or len(valor) != LARGO_DESCRIPTOR:
        return None
    try:
        numeros = [float(x) for x in valor]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) and -2 <= x <= 2 for x in numeros):
        return None
    return numeros


def descriptor_guardado(usuario_id):
    fila = consultar("SELECT descriptor, muestras, updated_at FROM usuario_rostros WHERE usuario_id = %s",
                     (usuario_id,), uno=True)
    if not fila:
        return None, None
    return json.loads(fila["descriptor"]), fila


# ------------------------------------------------------------------ registro desde Mi Perfil
@facial_bp.get("/api/rostro")
@login_requerido
def estado_rostro():
    _, fila = descriptor_guardado(g.usuario_token["id"])
    return jsonify(registrado=bool(fila), muestras=fila["muestras"] if fila else 0,
                   actualizado=fila["updated_at"].strftime("%d/%m/%Y %H:%M") if fila else None,
                   umbral=UMBRAL)


@facial_bp.post("/api/rostro")
@login_requerido
def registrar_rostro():
    datos = request.get_json(silent=True) or {}
    usuario_id = g.usuario_token["id"]
    fila = consultar("SELECT password_hash FROM users WHERE id = %s", (usuario_id,), uno=True)
    if not clave_correcta(datos.get("clave") or "", fila["password_hash"]):
        return jsonify(error="Confirma con tu contraseña actual para registrar tu rostro."), 400
    descriptores = [validar_descriptor(d) for d in (datos.get("descriptores") or [])]
    if len(descriptores) != MUESTRAS_REGISTRO or any(d is None for d in descriptores):
        return jsonify(error=f"Se necesitan {MUESTRAS_REGISTRO} capturas válidas del rostro."), 400
    # Las 3 capturas deben ser de la misma persona (evita mezclar rostros)
    maxima = max(distancia_euclidiana(a, b) for i, a in enumerate(descriptores) for b in descriptores[i + 1:])
    if maxima > UMBRAL_MISMA_PERSONA_REGISTRO:
        return jsonify(error="Las capturas no coinciden entre sí. Mantén solo tu rostro frente a la cámara e inténtalo otra vez.",
                       distancia=round(maxima, 4)), 400
    descriptor = [round(x, 6) for x in promedio(descriptores)]
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO usuario_rostros (usuario_id, descriptor, muestras, created_at, updated_at)
               VALUES (%s, %s, %s, NOW(), NOW())
               ON DUPLICATE KEY UPDATE descriptor = VALUES(descriptor), muestras = VALUES(muestras), updated_at = NOW()""",
            (usuario_id, json.dumps(descriptor), MUESTRAS_REGISTRO),
        )
        # Un rostro nuevo reinicia el contador de intentos fallidos
        cur.execute("""INSERT INTO login_facial_intentos (usuario_id, correo, exito, motivo, ip, created_at)
                       VALUES (%s, %s, 1, 'rostro registrado', %s, NOW())""",
                    (usuario_id, g.usuario_token["correo"], _ip()))
    con.commit()
    return jsonify(mensaje="Rostro registrado. Ya puedes iniciar sesión con reconocimiento facial.",
                   consistencia=round(maxima, 4)), 201


@facial_bp.delete("/api/rostro")
@login_requerido
def eliminar_rostro():
    con = conexion()
    with con.cursor() as cur:
        cur.execute("DELETE FROM usuario_rostros WHERE usuario_id = %s", (g.usuario_token["id"],))
    con.commit()
    return jsonify(mensaje="Se eliminó tu rostro. Solo podrás ingresar con tu contraseña.")


# ------------------------------------------------------------------ login facial
def _ip():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:45].split(",")[0].strip()


def _registrar_intento(usuario_id, correo, exito, distancia=None, motivo=None):
    con = conexion()
    with con.cursor() as cur:
        cur.execute(
            """INSERT INTO login_facial_intentos (usuario_id, correo, exito, distancia, motivo, ip, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
            (usuario_id, correo[:120], int(exito), distancia, motivo, _ip()),
        )
    con.commit()


def _fallos_recientes(usuario_id):
    """Fallos desde el último acierto, dentro de la ventana de bloqueo."""
    fila = consultar(
        f"""SELECT COUNT(*) AS fallos,
                   TIMESTAMPDIFF(SECOND, NOW(), MIN(created_at) + INTERVAL {MINUTOS_BLOQUEO} MINUTE) AS segundos
              FROM login_facial_intentos
             WHERE usuario_id = %s AND exito = 0
               AND created_at > NOW() - INTERVAL {MINUTOS_BLOQUEO} MINUTE
               AND id > COALESCE((SELECT MAX(id) FROM login_facial_intentos
                                   WHERE usuario_id = %s AND exito = 1), 0)""",
        (usuario_id, usuario_id), uno=True,
    )
    return int(fila["fallos"] or 0), max(int(fila["segundos"] or 0), 0)


@facial_bp.get("/api/login-facial/estado")
def estado_login_facial():
    """Antes de encender la cámara: indica si el correo tiene rostro registrado o está bloqueado.
    Así no se deja intentar el ingreso facial a una cuenta sin rostro."""
    correo = (request.args.get("correo") or "").strip().lower()
    usuario = consultar("SELECT id, activo FROM users WHERE correo = %s", (correo,), uno=True) if correo else None
    registrado = bool(usuario and usuario["activo"] and descriptor_guardado(usuario["id"])[1])
    if not registrado:
        return jsonify(registrado=False, bloqueado=False)
    fallos, segundos = _fallos_recientes(usuario["id"])
    if fallos >= MAX_INTENTOS:
        minutos = max(1, math.ceil(segundos / 60))
        return jsonify(registrado=True, bloqueado=True,
                       mensaje=f"Login facial bloqueado por {MAX_INTENTOS} intentos fallidos. Espera {minutos} min o usa tu contraseña.")
    return jsonify(registrado=True, bloqueado=False, intentos_restantes=MAX_INTENTOS - fallos)


@facial_bp.post("/api/login-facial")
def login_facial():
    datos = request.get_json(silent=True) or {}
    correo = (datos.get("correo") or "").strip().lower()
    descriptor = validar_descriptor(datos.get("descriptor"))
    if not correo or "@" not in correo:
        return jsonify(error="Escribe tu correo corporativo antes de usar el reconocimiento facial."), 400
    if descriptor is None:
        return jsonify(error="No se recibió un rostro válido. Inténtalo otra vez."), 400

    por_ip = consultar(
        f"""SELECT COUNT(*) AS n FROM login_facial_intentos
             WHERE ip = %s AND exito = 0 AND created_at > NOW() - INTERVAL {MINUTOS_BLOQUEO} MINUTE""",
        (_ip(),), uno=True)["n"]
    if por_ip >= MAX_INTENTOS_IP:
        return jsonify(error="Demasiados intentos desde este equipo. Espera unos minutos o usa tu contraseña.",
                       bloqueado=True), 429

    usuario = consultar(f"SELECT * FROM {V_USUARIOS_SESION} AS v WHERE v.correo = %s", (correo,), uno=True)
    if not usuario:
        _registrar_intento(None, correo, False, motivo="correo no existe")
        return jsonify(error="Rostro no reconocido para ese correo."), 401

    fallos, segundos = _fallos_recientes(usuario["id"])
    if fallos >= MAX_INTENTOS:
        minutos = max(1, math.ceil(segundos / 60))
        return jsonify(error=f"Login facial bloqueado por {MAX_INTENTOS} intentos fallidos. "
                             f"Espera {minutos} min o ingresa con tu contraseña.", bloqueado=True), 429

    error_cuenta = verificar_cuenta(usuario)
    if error_cuenta:
        _registrar_intento(usuario["id"], correo, False, motivo="cuenta no habilitada")
        return jsonify(error=error_cuenta), 403

    guardado, _ = descriptor_guardado(usuario["id"])
    if guardado is None:
        _registrar_intento(usuario["id"], correo, False, motivo="sin rostro registrado")
        return jsonify(error="Esta cuenta no tiene un rostro registrado. Ingresa con tu contraseña y regístralo en Mi Perfil.",
                       sin_registro=True), 404

    distancia = distancia_euclidiana(descriptor, guardado)
    if distancia > UMBRAL:
        _registrar_intento(usuario["id"], correo, False, round(distancia, 4), "rostro no coincide")
        quedan = MAX_INTENTOS - (fallos + 1)
        mensaje = "Rostro no reconocido."
        mensaje += f" Te quedan {quedan} intento(s)." if quedan > 0 else \
            f" Login facial bloqueado por {MINUTOS_BLOQUEO} min; usa tu contraseña."
        return jsonify(error=mensaje, intentos_restantes=max(quedan, 0), distancia=round(distancia, 4),
                       umbral=UMBRAL), 401

    # Coincide: mismo inicio de sesión que con contraseña (JWT en cookie HttpOnly)
    _registrar_intento(usuario["id"], correo, True, round(distancia, 4), "acceso concedido")
    recordar = bool(datos.get("recordar"))
    token, duracion = crear_token(usuario, recordar)
    registrar_acceso(usuario["id"])
    session.clear()
    llenar_sesion(usuario)
    destino = url_for("empresas.listado") if usuario["rol"] == ROL_SUPER else url_for("pantalla", pagina="tickets")
    respuesta = make_response(jsonify(ok=True, mensaje=f"Bienvenido, {usuario['nombre'].split()[0]}.",
                                      redirigir=destino, distancia=round(distancia, 4), umbral=UMBRAL))
    respuesta.set_cookie(config.COOKIE_TOKEN, token,
                         max_age=int(duracion.total_seconds()) if recordar else None,
                         httponly=True, samesite="Lax", secure=request.is_secure)
    return respuesta
