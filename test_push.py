import os
import json
from dotenv import load_dotenv
from db import obtener_conexion

# Cargar variables del .env
load_dotenv()

print("Verificando instalación de pywebpush...")
try:
    from pywebpush import webpush
    print("✅ pywebpush está instalado correctamente.")
except ImportError:
    print("❌ ERROR: pywebpush NO está instalado.")
    exit()

clave_privada = os.getenv("VAPID_PRIVATE_KEY")
if not clave_privada:
    print("❌ ERROR: No se encontró VAPID_PRIVATE_KEY en el archivo .env")
    exit()
else:
    print("✅ Llave VAPID privada cargada.")

print("\nBuscando suscripciones en la base de datos...")
con = obtener_conexion()
try:
    with con.cursor() as cur:
        cur.execute("SELECT * FROM push_suscripciones WHERE activo = 1")
        subs = cur.fetchall()
        print(f"✅ Se encontraron {len(subs)} suscripciones activas.")

        if not subs:
            print("❌ No hay navegadores suscritos. Entra a la web y dale a 'Activar Alertas Push'.")
        
        for sub in subs:
            print(f"Intentando enviar Push al usuario ID {sub['usuario_id']}...")
            payload = json.dumps({
                "title": "¡Prueba Nativa Exitosa!", 
                "body": "Esta es una notificación real del sistema operativo, con la pestaña cerrada.", 
                "url": "/sla"
            })
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"], 
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                    },
                    data=payload,
                    vapid_private_key=clave_privada,
                    vapid_claims={"sub": "mailto:soporte@mesadeayuda.pe"}
                )
                print("   ✅ Push enviado con éxito a este navegador.")
            except Exception as e:
                print(f"   ❌ Error al enviar a este navegador: {e}")
finally:
    con.close()