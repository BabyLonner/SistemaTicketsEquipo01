-- =========================================================
-- Mesa de Ayuda TI - Base de datos (MySQL / MariaDB)
-- Ejecutar en phpMyAdmin (pestaña SQL) o en la consola de MySQL
-- =========================================================

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS mesa_ayuda_ti
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE mesa_ayuda_ti;

-- Módulo 1: usuarios con rol y estado activo/inactivo
CREATE TABLE IF NOT EXISTS users (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  nombre      VARCHAR(120) NOT NULL,
  email       VARCHAR(160) NOT NULL UNIQUE,
  password    VARCHAR(100) NOT NULL,              -- hash bcrypt, nunca el texto plano
  rol         ENUM('Administrador', 'Técnico', 'Solicitante') NOT NULL DEFAULT 'Solicitante',
  empresa     VARCHAR(60)  NOT NULL,
  area        VARCHAR(60)  NULL,
  activo      TINYINT(1)   NOT NULL DEFAULT 1,
  created_at  DATETIME     NOT NULL
) ENGINE=InnoDB;

-- Tokens JWT invalidados al cerrar sesión
CREATE TABLE IF NOT EXISTS tokens_revocados (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  jti         VARCHAR(64) NOT NULL UNIQUE,
  created_at  DATETIME    NOT NULL
) ENGINE=InnoDB;

-- Módulo 2: tickets
CREATE TABLE IF NOT EXISTS tickets (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  asunto          VARCHAR(120) NOT NULL,
  descripcion     TEXT         NOT NULL,
  categoria       VARCHAR(40)  NOT NULL,
  prioridad       ENUM('Alta', 'Media', 'Baja') NOT NULL,
  estado          ENUM('Abierto', 'En proceso', 'Resuelto', 'Cerrado') NOT NULL DEFAULT 'Abierto',
  empresa         VARCHAR(60)  NOT NULL,
  solicitante_id  INT          NOT NULL,
  tecnico_id      INT          NULL,
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL,
  cerrado_at      DATETIME     NULL,
  CONSTRAINT fk_ticket_solicitante FOREIGN KEY (solicitante_id) REFERENCES users(id),
  CONSTRAINT fk_ticket_tecnico     FOREIGN KEY (tecnico_id)     REFERENCES users(id),
  INDEX idx_ticket_estado (estado),
  INDEX idx_ticket_empresa (empresa),
  INDEX idx_ticket_creado (created_at)
) ENGINE=InnoDB;

-- Módulo 2: fotos de evidencia (hasta 3 por ticket, se valida en Python)
CREATE TABLE IF NOT EXISTS ticket_fotos (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  ticket_id        INT          NOT NULL,
  archivo          VARCHAR(80)  NOT NULL UNIQUE,
  miniatura        VARCHAR(80)  NOT NULL UNIQUE,
  nombre_original  VARCHAR(200) NOT NULL,
  mime             VARCHAR(40)  NOT NULL,
  created_at       DATETIME     NOT NULL,
  CONSTRAINT fk_foto_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Módulo 3: historial (cada cambio de estado lleva comentario obligatorio)
CREATE TABLE IF NOT EXISTS ticket_historial (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  ticket_id        INT         NOT NULL,
  usuario_id       INT         NOT NULL,
  tipo             ENUM('creado', 'asignado', 'estado', 'comentario') NOT NULL,
  estado_anterior  VARCHAR(20) NULL,
  estado_nuevo     VARCHAR(20) NULL,
  texto            TEXT        NOT NULL,
  created_at       DATETIME    NOT NULL,
  CONSTRAINT fk_historial_ticket  FOREIGN KEY (ticket_id)  REFERENCES tickets(id) ON DELETE CASCADE,
  CONSTRAINT fk_historial_usuario FOREIGN KEY (usuario_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- Módulo 5: notificaciones internas
CREATE TABLE IF NOT EXISTS notificaciones (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id         INT          NOT NULL,
  tipo               ENUM('nuevo', 'asignacion', 'estado', 'comentario') NOT NULL,
  referencia_ticket  INT          NOT NULL,
  mensaje            VARCHAR(200) NOT NULL,
  leido              TINYINT(1)   NOT NULL DEFAULT 0,
  created_at         DATETIME     NOT NULL,
  CONSTRAINT fk_notif_usuario FOREIGN KEY (usuario_id)        REFERENCES users(id),
  CONSTRAINT fk_notif_ticket  FOREIGN KEY (referencia_ticket) REFERENCES tickets(id) ON DELETE CASCADE,
  INDEX idx_notif_usuario_leido (usuario_id, leido)
) ENGINE=InnoDB;
