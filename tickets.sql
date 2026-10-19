-- =====================================================================
--  TICKETS — Registro de tickets con evidencias
--  Tablas: tickets, ticket_evidencias
--  Compatible con MySQL 8 y MariaDB 10.4+ (XAMPP).
--
--  Orden de ejecución sugerido:
--    1. Script del módulo de usuarios (tabla users).
--    2. Este script.
--  Si el módulo de usuarios aún no tiene su script, el bloque "users" de abajo
--  crea una versión mínima SOLO si la tabla no existe (no la pisa).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sistema_tickets
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sistema_tickets;
SET NAMES utf8mb4;  -- evita que las tildes se guarden mal (Pérez -> PÃ©rez)

-- ---------------------------------------------------------------------
-- users (propiedad del módulo de usuarios). Solo para pruebas locales.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  nombre        VARCHAR(100) NOT NULL,
  correo        VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  rol           ENUM('Administrador','Técnico','Solicitante') NOT NULL DEFAULT 'Solicitante',
  activo        TINYINT(1) NOT NULL DEFAULT 1,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- tickets
--   * solicitante_id se llena en el servidor con el usuario del token
--     (solicitante automático): nunca viene del formulario.
--   * estado y tecnico_id los usa el MÓDULO 3 (asignación/estados).
--   * El código visible "TK-0001" se calcula al consultar (no se guarda).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  asunto          VARCHAR(120)  NOT NULL,
  descripcion     VARCHAR(1000) NOT NULL,
  categoria       VARCHAR(40)   NOT NULL,
  area            VARCHAR(40)   NOT NULL,
  prioridad       ENUM('Alta','Media','Baja') NOT NULL DEFAULT 'Media',
  estado          ENUM('Abierto','En proceso','Resuelto','Cerrado') NOT NULL DEFAULT 'Abierto',
  solicitante_id  INT NOT NULL,
  tecnico_id      INT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_tickets_solicitante FOREIGN KEY (solicitante_id) REFERENCES users(id),
  CONSTRAINT fk_tickets_tecnico     FOREIGN KEY (tecnico_id)     REFERENCES users(id),
  INDEX idx_tickets_estado      (estado),
  INDEX idx_tickets_prioridad   (prioridad),
  INDEX idx_tickets_solicitante (solicitante_id),
  INDEX idx_tickets_created     (created_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- ticket_evidencias  (máximo 3 por ticket, se controla en Python
-- dentro de una transacción con SELECT ... FOR UPDATE)
--   * archivo / miniatura: rutas RELATIVAS a la carpeta /uploads
--     ej. tickets/7/3f2a...c1.jpg  y  tickets/7/3f2a...c1_min.jpg
--   * mime_type: el tipo REAL detectado por la firma binaria del archivo.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_evidencias (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  ticket_id       INT NOT NULL,
  nombre_original VARCHAR(255) NOT NULL,
  archivo         VARCHAR(255) NOT NULL,
  miniatura       VARCHAR(255) NOT NULL,
  mime_type       VARCHAR(30)  NOT NULL,
  tamano_bytes    INT NOT NULL,
  ancho           INT NOT NULL,
  alto            INT NOT NULL,
  subido_por      INT NOT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_evidencias_ticket  FOREIGN KEY (ticket_id)  REFERENCES tickets(id) ON DELETE CASCADE,
  CONSTRAINT fk_evidencias_usuario FOREIGN KEY (subido_por) REFERENCES users(id),
  INDEX idx_evidencias_ticket (ticket_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Datos de prueba (solo si la tabla users está vacía).
-- La contraseña no importa aquí; el login es del módulo de usuarios.
-- ---------------------------------------------------------------------
INSERT INTO users (nombre, correo, password_hash, rol)
SELECT * FROM (
  SELECT 'Juan Pérez'    AS nombre, 'solicitante@tickets.com' AS correo, 'pendiente-modulo-1' AS password_hash, 'Solicitante'   AS rol UNION ALL
  SELECT 'Luis Ramos',              'tecnico@tickets.com',             'pendiente-modulo-1',                  'Técnico'              UNION ALL
  SELECT 'Ana Díaz',                'admin@tickets.com',               'pendiente-modulo-1',                  'Administrador'
) AS semilla
WHERE NOT EXISTS (SELECT 1 FROM users);
