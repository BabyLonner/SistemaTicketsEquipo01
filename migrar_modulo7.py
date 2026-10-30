"""MÓDULO 7 — Agrega a una base de datos EXISTENTE lo necesario para las alertas Web Push de SLA.

NO borra datos. Se puede ejecutar varias veces sin problema (revisa antes de crear).
Funciona en MySQL 8 (PythonAnywhere) y en MariaDB (XAMPP).
    Local:          python migrar_modulo7.py
    PythonAnywhere: python3.13 migrar_modulo7.py

Hace dos cosas:
  1. Columnas tickets.alerta_sla_enviada, tickets.escalado_sla y tickets.fecha_escalamiento
  2. Tabla push_suscripciones (suscripciones Web Push de cada usuario/navegador)
"""
from db import obtener_conexion

COLUMNAS = {
    "alerta_sla_enviada": "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Aviso preventivo enviado al técnico (amarillo)'",
    "escalado_sla": "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Ticket vencido (rojo), escalado al supervisor'",
    "fecha_escalamiento": "DATETIME NULL",
}

TABLA_PUSH = """CREATE TABLE IF NOT EXISTS push_suscripciones (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario_id INT UNSIGNED NOT NULL,
    endpoint VARCHAR(500) NOT NULL,
    p256dh VARCHAR(255) NOT NULL,
    auth VARCHAR(255) NOT NULL,
    user_agent VARCHAR(255) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_push_endpoint UNIQUE (endpoint),
    CONSTRAINT fk_push_usuario FOREIGN KEY (usuario_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""


def main():
    con = obtener_conexion()
    try:
        with con.cursor() as cur:
            for nombre, definicion in COLUMNAS.items():
                cur.execute(
                    """SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tickets' AND COLUMN_NAME = %s""",
                    (nombre,),
                )
                if cur.fetchone()["n"]:
                    print(f"  ya existe tickets.{nombre}")
                else:
                    cur.execute(f"ALTER TABLE tickets ADD COLUMN {nombre} {definicion}")
                    print(f"  agregada tickets.{nombre}")
            cur.execute(TABLA_PUSH)
            print("  tabla push_suscripciones lista")
        con.commit()
    finally:
        con.close()
    print("Listo: Módulo 7 aplicado (los datos existentes no se tocaron).")


if __name__ == "__main__":
    main()
