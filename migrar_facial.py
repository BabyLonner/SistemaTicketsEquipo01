"""Agrega las tablas del login facial a una base que YA tiene datos (no borra nada).

Úsalo si ya cargaste la versión 2.1 y no quieres volver a ejecutar inicializar_bd.py:
    python migrar_facial.py        (en PythonAnywhere: python3.13 migrar_facial.py)
"""
from db import obtener_conexion

SENTENCIAS = [
    """CREATE TABLE IF NOT EXISTS usuario_rostros (
      usuario_id  INT UNSIGNED     NOT NULL,
      descriptor  TEXT             NOT NULL,
      muestras    TINYINT UNSIGNED NOT NULL DEFAULT 3,
      created_at  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (usuario_id),
      CONSTRAINT fk_rostros_usuario FOREIGN KEY (usuario_id) REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS login_facial_intentos (
      id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
      usuario_id  INT UNSIGNED  NULL,
      correo      VARCHAR(120)  NOT NULL,
      exito       TINYINT(1)    NOT NULL DEFAULT 0,
      distancia   DECIMAL(6,4)  NULL,
      motivo      VARCHAR(80)   NULL,
      ip          VARCHAR(45)   NULL,
      created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      CONSTRAINT fk_intentos_usuario FOREIGN KEY (usuario_id) REFERENCES users (id) ON DELETE CASCADE,
      INDEX idx_intentos_usuario (usuario_id, created_at),
      INDEX idx_intentos_ip (ip, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

if __name__ == "__main__":
    con = obtener_conexion()
    with con.cursor() as cur:
        for sql in SENTENCIAS:
            cur.execute(sql)
    con.commit()
    con.close()
    print("Listo: tablas usuario_rostros y login_facial_intentos creadas (los datos existentes no se tocaron).")
