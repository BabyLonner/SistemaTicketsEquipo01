"""MÓDULO 4 — Agrega a una base de datos EXISTENTE lo necesario para los avisos por WhatsApp.

NO borra datos. Se puede ejecutar varias veces sin problema (revisa antes de crear).
    Local:          python migrar_modulo4.py
    PythonAnywhere: consola Bash, dentro de la carpeta del proyecto: python migrar_modulo4.py

Hace dos cosas:
  1. Columna users.telefono  (número de WhatsApp del técnico, se llena desde "Mi Perfil")
  2. Tabla mensajes_externos (registro de cada mensaje enviado y su estado)
"""
from db import obtener_conexion

TABLA_MENSAJES = """
CREATE TABLE IF NOT EXISTS mensajes_externos (
  id               INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id       INT UNSIGNED  NOT NULL,
  ticket_id        INT UNSIGNED  NULL,
  tecnico_id       INT UNSIGNED  NOT NULL,
  enviado_por      INT UNSIGNED  NULL,
  canal            ENUM('WHATSAPP','SMS') NOT NULL DEFAULT 'WHATSAPP',
  motivo           ENUM('ASIGNACION','REASIGNACION','PRUEBA') NOT NULL DEFAULT 'ASIGNACION',
  telefono         VARCHAR(15)   NULL,
  mensaje          VARCHAR(600)  NOT NULL,
  proveedor_id     VARCHAR(64)   NULL,
  estado           ENUM('PENDIENTE','ENVIADO','ENTREGADO','LEIDO','FALLIDO') NOT NULL DEFAULT 'PENDIENTE',
  error_detalle    VARCHAR(255)  NULL,
  intentos         TINYINT UNSIGNED NOT NULL DEFAULT 1,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_msg_empresa FOREIGN KEY (empresa_id)  REFERENCES empresas (id),
  CONSTRAINT fk_msg_ticket  FOREIGN KEY (ticket_id)   REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_msg_tecnico FOREIGN KEY (tecnico_id)  REFERENCES users (id)   ON DELETE CASCADE,
  CONSTRAINT fk_msg_autor   FOREIGN KEY (enviado_por) REFERENCES users (id)   ON DELETE SET NULL,
  INDEX idx_msg_empresa_fecha (empresa_id, created_at),
  INDEX idx_msg_proveedor (proveedor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def main():
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'telefono'"""
            )
            if cur.fetchone()["n"]:
                print("· users.telefono ya existía")
            else:
                cur.execute("ALTER TABLE users ADD COLUMN telefono VARCHAR(15) NULL AFTER correo")
                print("✓ Columna users.telefono agregada")
            cur.execute(TABLA_MENSAJES)
            print("✓ Tabla mensajes_externos lista")
        con.commit()
    finally:
        con.close()
    print("Migración del módulo 4 terminada. No se borró ningún dato.")


if __name__ == "__main__":
    main()
