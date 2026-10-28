"""MÓDULO 3 (avance 2) — Agrega a una base de datos EXISTENTE lo necesario para las etiquetas QR.

NO borra datos. Se puede ejecutar varias veces sin problema (revisa antes de crear).
    Local:          python migrar_modulo3_qr.py
    PythonAnywhere: consola Bash, dentro de la carpeta del proyecto: python migrar_modulo3_qr.py

Hace dos cosas:
  1. Tabla equipos         (inventario de equipos, cada uno con su qr_token aleatorio)
  2. Columna tickets.equipo_id  (equipo escaneado al registrar el ticket)

Si la base es nueva, no hace falta: python inicializar_bd.py ya crea todo con datos de ejemplo.
"""
from db import obtener_conexion

TABLA_EQUIPOS = """
CREATE TABLE IF NOT EXISTS equipos (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  area_id     INT UNSIGNED  NULL,
  codigo      VARCHAR(30)   NOT NULL,
  nombre      VARCHAR(100)  NOT NULL,
  tipo        ENUM('Laptop','PC de escritorio','Impresora','Monitor','Proyector','Equipo de red','Teléfono','Otro') NOT NULL DEFAULT 'Otro',
  marca       VARCHAR(50)   NULL,
  modelo      VARCHAR(60)   NULL,
  serie       VARCHAR(60)   NULL,
  ubicacion   VARCHAR(120)  NOT NULL,
  qr_token    VARCHAR(24)   COLLATE utf8mb4_bin NOT NULL,
  activo      TINYINT(1)    NOT NULL DEFAULT 1,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_equipos_token          UNIQUE (qr_token),
  CONSTRAINT uq_equipos_empresa_codigo UNIQUE (empresa_id, codigo),
  CONSTRAINT ck_equipos_nombre         CHECK (CHAR_LENGTH(TRIM(nombre)) >= 3),
  CONSTRAINT fk_equipos_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT fk_equipos_area    FOREIGN KEY (area_id)    REFERENCES areas (id) ON DELETE SET NULL,
  INDEX idx_equipos_empresa (empresa_id, activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _existe_columna(cur, tabla, columna):
    cur.execute(
        """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (tabla, columna),
    )
    return cur.fetchone()["n"] > 0


def main():
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            cur.execute(TABLA_EQUIPOS)
            print("✓ Tabla equipos lista")
            if _existe_columna(cur, "tickets", "equipo_id"):
                print("· tickets.equipo_id ya existía")
            else:
                cur.execute("ALTER TABLE tickets ADD COLUMN equipo_id INT UNSIGNED NULL AFTER tecnico_id")
                cur.execute("""ALTER TABLE tickets ADD CONSTRAINT fk_tickets_equipo
                               FOREIGN KEY (equipo_id) REFERENCES equipos (id) ON DELETE SET NULL""")
                print("✓ Columna tickets.equipo_id agregada")
        con.commit()
    finally:
        con.close()
    print("Migración del módulo 3 (QR) terminada. No se borró ningún dato.")


if __name__ == "__main__":
    main()
