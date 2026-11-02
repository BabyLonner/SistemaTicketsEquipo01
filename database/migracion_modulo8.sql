-- =====================================================================
--  MODULO 8  -  Migracion: solo crea las tablas nuevas (NO borra datos).
--  Usar en PythonAnywhere en lugar de inicializar_bd.py:
--    python3.13 migrar_modulo8.py
--  migrar_modulo8.py ademas agrega la columna reporte_destinatarios.semanal si la tabla ya existia.
--  Si pegas este contenido en la consola MySQL / phpMyAdmin y la tabla ya existia, ejecuta tambien:
--    ALTER TABLE reporte_destinatarios ADD COLUMN semanal TINYINT(1) NOT NULL DEFAULT 1 AFTER correo;
-- =====================================================================

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS reportes_generados (
  id             INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo         VARCHAR(32)   COLLATE utf8mb4_bin NOT NULL,
  empresa_id     INT UNSIGNED  NOT NULL,
  periodo_desde  DATE          NULL,
  periodo_hasta  DATE          NULL,
  filtros        VARCHAR(500)  NOT NULL,
  total_tickets  INT UNSIGNED  NOT NULL DEFAULT 0,
  hash_sha256    CHAR(64)      NOT NULL,
  generado_por   INT UNSIGNED  NULL,
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_reportes_codigo  UNIQUE (codigo),
  CONSTRAINT ck_reportes_hash    CHECK (hash_sha256 REGEXP '^[0-9a-f]{64}$'),
  CONSTRAINT fk_reportes_empresa FOREIGN KEY (empresa_id)   REFERENCES empresas (id) ON DELETE CASCADE,
  CONSTRAINT fk_reportes_usuario FOREIGN KEY (generado_por) REFERENCES users (id)    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reporte_destinatarios (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  correo      VARCHAR(150)  NOT NULL,
  semanal     TINYINT(1)    NOT NULL DEFAULT 1,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_destinatario  UNIQUE (empresa_id, correo),
  CONSTRAINT fk_dest_empresa  FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reporte_programacion (
  empresa_id  INT UNSIGNED      NOT NULL,
  activo      TINYINT(1)        NOT NULL DEFAULT 1,
  dia_semana  TINYINT UNSIGNED  NOT NULL DEFAULT 0,
  updated_at  DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (empresa_id),
  CONSTRAINT ck_programacion_dia CHECK (dia_semana <= 6),
  CONSTRAINT fk_prog_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reporte_envios (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id      INT UNSIGNED  NOT NULL,
  origen          ENUM('manual','automatico') NOT NULL,
  periodo_desde   DATE          NOT NULL,
  periodo_hasta   DATE          NOT NULL,
  destinatarios   VARCHAR(1000) NOT NULL,
  codigo_reporte  VARCHAR(32)   COLLATE utf8mb4_bin NULL,
  estado          ENUM('ok','error') NOT NULL,
  detalle         VARCHAR(500)  NULL,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_envio_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE,
  INDEX idx_envio_periodo (empresa_id, origen, periodo_desde, estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
