"""MÓDULO 6 — Agrega a una base de datos EXISTENTE la base de conocimiento del asistente con IA.

NO borra datos. Se puede ejecutar varias veces sin problema (revisa antes de crear).
Funciona en MySQL 8 (PythonAnywhere) y en MariaDB (XAMPP).
    Local:          python migrar_modulo6.py
    PythonAnywhere: python3.13 migrar_modulo6.py
(También se puede importar database/migracion_modulo6.sql en phpMyAdmin.)

Hace tres cosas:
  1. Tabla kb_articulos: artículos de solución (los únicos que puede usar el asistente).
  2. Tabla kb_consultas: cada consulta al asistente y su resultado (RESUELTO sin ticket o TICKET).
  3. Registra 12 artículos generales (visibles para todas las empresas) si la tabla está vacía.
     Son los artículos que puede usar el asistente; se agregan más con INSERT en esta tabla.
"""
from db import obtener_conexion

TABLA_ARTICULOS = """CREATE TABLE IF NOT EXISTS kb_articulos (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id      INT UNSIGNED  NULL,                     -- NULL = artículo general (todas las empresas)
  categoria_id    INT UNSIGNED  NULL,
  titulo          VARCHAR(150)  NOT NULL,
  resumen         VARCHAR(300)  NOT NULL,
  contenido       TEXT          NOT NULL,                 -- pasos de la solución
  palabras_clave  VARCHAR(300)  NOT NULL DEFAULT '',
  activo          TINYINT(1)    NOT NULL DEFAULT 1,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_kb_articulos_empresa (empresa_id, activo),
  CONSTRAINT fk_kb_art_empresa   FOREIGN KEY (empresa_id)   REFERENCES empresas (id)   ON DELETE CASCADE,
  CONSTRAINT fk_kb_art_categoria FOREIGN KEY (categoria_id) REFERENCES categorias (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""

TABLA_CONSULTAS = """CREATE TABLE IF NOT EXISTS kb_consultas (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id      INT UNSIGNED  NOT NULL,
  usuario_id      INT UNSIGNED  NOT NULL,
  pregunta        VARCHAR(600)  NOT NULL,
  respuesta       TEXT          NULL,
  articulos       VARCHAR(100)  NULL,                     -- ids de los artículos usados: "3,7"
  modo            ENUM('IA','LOCAL','CACHE','SIN_ARTICULOS') NOT NULL,
  tokens_entrada  INT UNSIGNED  NOT NULL DEFAULT 0,
  tokens_salida   INT UNSIGNED  NOT NULL DEFAULT 0,
  resultado       ENUM('PENDIENTE','RESUELTO','TICKET') NOT NULL DEFAULT 'PENDIENTE',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cerrado_at      DATETIME      NULL,
  PRIMARY KEY (id),
  KEY ix_kb_consultas_empresa (empresa_id, created_at),
  KEY ix_kb_consultas_usuario (usuario_id, created_at),
  CONSTRAINT fk_kb_con_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE,
  CONSTRAINT fk_kb_con_usuario FOREIGN KEY (usuario_id) REFERENCES users (id)    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""

# (categoria_id, titulo, resumen, palabras_clave, contenido)
# Categorías: 1 Hardware, 2 Software, 3 Red e internet, 4 Accesos y cuentas, 5 Impresoras, 6 Correo
ARTICULOS = [
    (5, "La impresora no imprime o deja los documentos en cola",
     "Qué revisar cuando mandas a imprimir y no sale nada, o los documentos se quedan en espera.",
     "impresora imprimir no imprime cola trabajos atascado pendiente impresión",
     "1. Revisa que la impresora esté encendida y sin luces de error (naranja o roja).\n"
     "2. Comprueba que tenga papel y que la bandeja esté bien cerrada.\n"
     "3. En la PC abre Configuración > Bluetooth y dispositivos > Impresoras y escáneres, elige la impresora y pulsa «Abrir cola de impresión».\n"
     "4. Cancela los documentos atascados y vuelve a imprimir.\n"
     "5. Verifica que elegiste la impresora correcta al imprimir (no «Microsoft Print to PDF»).\n"
     "6. Apaga la impresora 30 segundos y vuelve a encenderla.\n"
     "Si sigue sin imprimir o muestra un código de error, crea un ticket indicando el modelo y el mensaje."),
    (5, "Atasco de papel en la impresora",
     "Cómo retirar una hoja atascada sin dañar la impresora.",
     "papel atascado atasco hoja trabada impresora arruga",
     "1. Apaga la impresora y espera a que se enfríe (la zona del fusor quema).\n"
     "2. Abre las tapas que indique la pantalla de la impresora.\n"
     "3. Retira la hoja jalándola con las dos manos, despacio y en el sentido en que avanza el papel.\n"
     "4. Revisa que no queden pedazos de papel dentro.\n"
     "5. Airea el papel, colócalo derecho y no llenes la bandeja por encima de la marca.\n"
     "Si el atasco se repite o se rompió alguna pieza, crea un ticket: no uses objetos metálicos para sacar el papel."),
    (3, "No tengo internet en mi computadora",
     "Pasos básicos cuando la PC no navega o aparece «Sin conexión a internet».",
     "internet red sin conexion navega wifi cable lento pagina carga desconectado",
     "1. Revisa si otros compañeros tienen internet: si nadie tiene, es una caída general y TI ya está trabajando.\n"
     "2. Si usas cable, comprueba que esté bien conectado a la PC y a la toma de la pared (debe haber luz en el puerto).\n"
     "3. Si usas wifi, desconéctate y vuelve a conectarte a la red de la empresa.\n"
     "4. Haz clic derecho en el ícono de red > «Solucionar problemas».\n"
     "5. Reinicia la computadora.\n"
     "Si solo a ti te falla después de estos pasos, crea un ticket indicando tu ubicación y si usas cable o wifi."),
    (3, "La VPN no conecta desde casa",
     "Qué hacer cuando no puedes entrar a los sistemas de la empresa trabajando de forma remota.",
     "vpn remoto casa conectar teletrabajo acceso externo forticlient",
     "1. Verifica primero que tu internet de casa funcione abriendo cualquier página.\n"
     "2. Cierra por completo el programa de VPN y vuelve a abrirlo.\n"
     "3. Revisa que la fecha y hora de tu computadora sean correctas.\n"
     "4. Escribe tu usuario sin el @dominio, solo la parte anterior.\n"
     "5. Si usa doble factor, confirma la notificación en tu celular antes de que pase 1 minuto.\n"
     "Si aparece un error de certificado o de credenciales, crea un ticket con una captura del mensaje."),
    (4, "Olvidé mi contraseña o mi cuenta está bloqueada",
     "Cómo recuperar el acceso a tu cuenta de Windows o del correo.",
     "contraseña clave olvide bloqueada cuenta acceso usuario restablecer password expiró caducó",
     "1. Si la cuenta se bloqueó por varios intentos fallidos, espera 15 minutos antes de volver a intentar.\n"
     "2. Revisa que la tecla Bloq Mayús esté apagada y que el teclado esté en español.\n"
     "3. Si tu contraseña expiró, Windows te pedirá una nueva: debe tener al menos 8 caracteres, con mayúscula, número y símbolo.\n"
     "4. Si no recuerdas tu contraseña, el restablecimiento lo hace TI: crea un ticket en la categoría «Accesos y cuentas».\n"
     "Importante: TI nunca te pedirá tu contraseña por correo, WhatsApp ni teléfono."),
    (6, "El correo no envía, no recibe o Outlook no sincroniza",
     "Soluciones cuando los correos se quedan en la Bandeja de salida o no llegan.",
     "correo outlook email enviar recibir sincroniza bandeja salida mensajes llega llegan entrada",
     "1. Revisa que tengas internet abriendo cualquier página.\n"
     "2. En Outlook mira abajo a la derecha: si dice «Desconectado» o «Trabajar sin conexión», ve a Enviar y recibir > Trabajar sin conexión para desactivarlo.\n"
     "3. Revisa si el correo pesa más de 20 MB: los adjuntos grandes no se envían; compártelos con un enlace.\n"
     "4. Cierra Outlook por completo y vuelve a abrirlo.\n"
     "5. Prueba entrar a tu correo desde el navegador (Outlook web). Si ahí funciona, el problema es solo del programa.\n"
     "Si tu buzón está lleno o sigue sin sincronizar, crea un ticket en la categoría «Correo»."),
    (1, "Mi computadora está muy lenta",
     "Acciones rápidas para mejorar el rendimiento de la PC.",
     "lenta lento computadora pc laptop demora tarda congela cuelga rendimiento",
     "1. Reinicia la computadora (no solo la suspendas): muchos problemas se resuelven así.\n"
     "2. Cierra los programas y pestañas del navegador que no estés usando.\n"
     "3. Abre el Administrador de tareas (Ctrl + Shift + Esc) y revisa qué programa usa más CPU o memoria.\n"
     "4. Revisa el espacio en el disco C: debe tener al menos 10 % libre (vacía la papelera y borra descargas que no uses).\n"
     "5. Deja que terminen las actualizaciones de Windows y reinicia.\n"
     "Si sigue lenta, crea un ticket indicando desde cuándo pasa y qué programas usas."),
    (1, "El monitor no muestra imagen",
     "Qué revisar cuando la pantalla se queda negra o dice «Sin señal».",
     "monitor pantalla negra imagen sin señal no prende enciende video",
     "1. Revisa que el monitor esté encendido (luz del botón de encendido).\n"
     "2. Comprueba que el cable de video (HDMI o DisplayPort) esté bien conectado en el monitor y en la PC.\n"
     "3. Si la PC tiene dos salidas de video, prueba conectar el cable en la otra.\n"
     "4. En laptops, presiona Windows + P y elige «Duplicar».\n"
     "5. Mueve el mouse o presiona una tecla: puede estar en suspensión.\n"
     "Si la PC no enciende o el monitor sigue sin señal, crea un ticket en la categoría «Hardware»."),
    (2, "Excel u otro programa se cierra solo o no responde",
     "Qué hacer cuando un programa se congela o se cierra sin avisar.",
     "excel word programa se cierra no responde congela error office aplicacion cuelga",
     "1. Espera un minuto: a veces el programa está procesando un archivo grande.\n"
     "2. Si no responde, ciérralo desde el Administrador de tareas (Ctrl + Shift + Esc) > Finalizar tarea.\n"
     "3. Al volver a abrirlo, recupera tu trabajo desde el panel «Recuperación de documentos».\n"
     "4. Si falla con un archivo específico, prueba con otro archivo: si los demás funcionan, el archivo puede estar dañado.\n"
     "5. Reinicia la computadora.\n"
     "Si el programa se sigue cerrando, crea un ticket con el nombre del programa y el mensaje de error."),
    (4, "Solicitar acceso a un sistema o carpeta compartida",
     "Cómo pedir permisos nuevos a un sistema, carpeta o aplicación de la empresa.",
     "acceso permiso sistema carpeta compartida erp usuario nuevo alta perfil",
     "Los accesos nuevos siempre los habilita TI y deben estar autorizados por tu jefe inmediato.\n"
     "1. Crea un ticket en la categoría «Accesos y cuentas».\n"
     "2. Indica el sistema o la carpeta, el tipo de permiso (consulta o edición) y el nombre de tu jefe que lo autoriza.\n"
     "3. TI te avisará por el ticket cuando el acceso esté listo.\n"
     "Este caso necesita un técnico: no se puede resolver sin crear el ticket."),
    (1, "El teclado o el mouse no funcionan",
     "Revisión rápida de teclados y mouse con cable o inalámbricos.",
     "teclado mouse raton no funciona inalambrico usb teclas cursor",
     "1. Si es con cable, desconéctalo y conéctalo en otro puerto USB.\n"
     "2. Si es inalámbrico, cambia las pilas y revisa que el receptor USB esté conectado.\n"
     "3. Revisa que el interruptor de encendido debajo del mouse o del teclado esté en ON.\n"
     "4. Reinicia la computadora.\n"
     "Si sigue sin funcionar, crea un ticket: TI puede prestarte uno mientras se revisa."),
    (6, "Recibí un correo sospechoso (phishing)",
     "Cómo reconocer y reportar correos que intentan robar tus datos.",
     "correo sospechoso phishing fraude enlace virus estafa adjunto falso raro extraño desconocido",
     "1. No abras enlaces ni archivos adjuntos del correo.\n"
     "2. Desconfía si te pide tu contraseña, datos bancarios o te apura con amenazas.\n"
     "3. Revisa la dirección real del remitente: los correos falsos imitan nombres conocidos.\n"
     "4. No respondas el correo.\n"
     "5. Si ya hiciste clic o escribiste tu contraseña, crea un ticket de inmediato con prioridad Alta y cambia tu contraseña.\n"
     "Si no hiciste clic, puedes eliminarlo."),
]

INSERTAR = """INSERT INTO kb_articulos (empresa_id, categoria_id, titulo, resumen, palabras_clave, contenido)
              VALUES (NULL, %s, %s, %s, %s, %s)"""


def main():
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            cur.execute(TABLA_ARTICULOS)
            print("  tabla kb_articulos lista")
            cur.execute(TABLA_CONSULTAS)
            print("  tabla kb_consultas lista")
            cur.execute("SELECT COUNT(*) AS n FROM kb_articulos")
            if cur.fetchone()["n"]:
                # Ya estaban cargados: solo se actualizan las palabras clave de los artículos generales
                for _cat, titulo, _res, claves, _cont in ARTICULOS:
                    cur.execute("UPDATE kb_articulos SET palabras_clave = %s WHERE empresa_id IS NULL AND titulo = %s",
                                (claves, titulo))
                print("  ya hay artículos: se actualizaron las palabras clave de los artículos generales")
            else:
                cur.executemany(INSERTAR, ARTICULOS)
                print(f"  {len(ARTICULOS)} artículos generales de ejemplo cargados")
        con.commit()
    finally:
        con.close()
    print("Listo: Módulo 6 aplicado (los datos existentes no se tocaron).")


if __name__ == "__main__":
    main()
