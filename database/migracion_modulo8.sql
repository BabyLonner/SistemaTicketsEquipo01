-- =====================================================================
--  MODULO 8  -  Migracion: solo crea la tabla nueva (NO borra datos).
--  Usar en PythonAnywhere en lugar de inicializar_bd.py:
--    mysql -u jcachay -h jcachay.mysql.pythonanywhere-services.com -p 'jcachay$dawagr1' < database/migracion_modulo8.sql
--  o pegar este contenido en la consola MySQL / phpMyAdmin.
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
