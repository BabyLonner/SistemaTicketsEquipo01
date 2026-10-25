-- =====================================================================
--  MESA DE AYUDA TI — VERSIÓN SIN TRIGGERS NI PROCEDIMIENTOS
--  (para servidores donde no se permite CREATE TRIGGER / PROCEDURE,
--   como PythonAnywhere). Las reglas que hacían los triggers ahora
--   las hace tickets.py: empresa, correlativo, área, fecha límite,
--   historial y notificaciones del ticket nuevo.
--  Se puede pegar en la consola MySQL o importar desde Bash:
--    mysql -u USUARIO -h USUARIO.mysql.pythonanywhere-services.com -p 'USUARIO$base' < mesa_ayuda_ti_sin_triggers.sql
--  ⚠ Borra y vuelve a crear todas las tablas (datos incluidos).
-- =====================================================================

--  MESA DE AYUDA TI — Base de datos del sistema de gestión de tickets
--  Un solo sistema para las 6 empresas del grupo (multiempresa)
--  Motor: MySQL 8.0 / MariaDB 10.4+ (XAMPP) — InnoDB, utf8mb4
-- ---------------------------------------------------------------------
--  CÓMO SE SEPARA CADA EMPRESA
--   * La empresa se reconoce por el dominio del correo (empresa_dominios).
--   * Cada usuario, ticket y reporte tiene empresa_id.
--   * Los triggers impiden mezclar empresas (técnicos, comentarios,
--     evidencias y notificaciones siempre de la misma empresa).
--   * Cada empresa tiene su identidad: título, colores y logo.
--   * Cada empresa numera sus tickets por separado (EPS-0001, AGF-0001...).
-- ---------------------------------------------------------------------
--  Módulo 1  Autenticación y usuarios ..... empresas, empresa_dominios, areas, users, tokens_revocados
--  Módulo 2  Tickets con evidencias ........ categorias, prioridades, tickets, ticket_evidencias
--  Módulo 3  Asignación, estados, historial  ticket_historial + sp_asignar_ticket / sp_cambiar_estado
--  Módulo 4  SLA y semáforo ................ prioridades.sla_horas, tickets.fecha_limite, vista v_tickets
--  Módulo 5  Notificaciones internas ....... notificaciones (las genera un trigger del historial)
--  Módulo 6  Dashboard y reportes .......... vistas v_tickets, v_dashboard_* y consultas GROUP BY
-- ---------------------------------------------------------------------
--  En PythonAnywhere la base se crea desde la pestaña "Databases"
--  (se llama Grupo01$tickets). En local, descomenta estas dos líneas:
--
--  CREATE DATABASE IF NOT EXISTS mesa_ayuda_ti CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--  USE mesa_ayuda_ti;
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW IF EXISTS v_dashboard_responsables, v_dashboard_resumen, v_notificaciones_pendientes,
                    v_ticket_timeline, v_tickets, v_usuarios_sesion;
DROP TRIGGER IF EXISTS trg_users_antes_insertar;
DROP TRIGGER IF EXISTS trg_users_antes_actualizar;
DROP TRIGGER IF EXISTS trg_tickets_antes_insertar;
DROP TRIGGER IF EXISTS trg_tickets_despues_insertar;
DROP TRIGGER IF EXISTS trg_tickets_antes_actualizar;
DROP TRIGGER IF EXISTS trg_evidencias_antes_insertar;
DROP TRIGGER IF EXISTS trg_historial_antes_insertar;
DROP TRIGGER IF EXISTS trg_historial_notificar;
DROP TABLE IF EXISTS notificaciones, ticket_historial, ticket_evidencias, tickets,
                     tokens_revocados, users, areas, categorias, prioridades,
                     empresa_dominios, empresas;

SET FOREIGN_KEY_CHECKS = 1;


-- =====================================================================
--  MÓDULO 1 — Empresas, áreas y usuarios
-- =====================================================================

-- Las 6 empresas del grupo que comparten el sistema, con su identidad visual
CREATE TABLE empresas (
  id                INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo            VARCHAR(20)   COLLATE utf8mb4_bin NOT NULL, -- identificador corto: 'epsel', 'agrofutura'
  nombre            VARCHAR(80)   NOT NULL,                    -- nombre comercial
  razon_social      VARCHAR(150)  NULL,
  ruc               CHAR(11)      NULL,
  prefijo_ticket    VARCHAR(5)    COLLATE utf8mb4_bin NOT NULL, -- EPS -> tickets EPS-0001, EPS-0002...
  titulo_sistema    VARCHAR(80)   NOT NULL,                    -- título que se muestra al iniciar sesión
  color_primario    CHAR(7)       NOT NULL,                    -- #RRGGBB
  color_secundario  CHAR(7)       NOT NULL,                    -- #RRGGBB (fondos suaves, insignias)
  logo_url          VARCHAR(255)  NULL,                        -- p. ej. /static/img/logos/epsel.png
  ultimo_ticket     INT UNSIGNED  NOT NULL DEFAULT 0,          -- correlativo de tickets de la empresa
  activo            TINYINT(1)    NOT NULL DEFAULT 1,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_empresas_codigo   UNIQUE (codigo),
  CONSTRAINT uq_empresas_nombre   UNIQUE (nombre),
  CONSTRAINT uq_empresas_ruc      UNIQUE (ruc),
  CONSTRAINT uq_empresas_prefijo  UNIQUE (prefijo_ticket),
  CONSTRAINT ck_empresas_codigo   CHECK (codigo REGEXP '^[a-z0-9-]+$'),
  CONSTRAINT ck_empresas_ruc      CHECK (ruc IS NULL OR ruc REGEXP '^[0-9]{11}$'),
  CONSTRAINT ck_empresas_prefijo  CHECK (prefijo_ticket REGEXP '^[A-Z]{2,5}$'),
  CONSTRAINT ck_empresas_color1   CHECK (color_primario   REGEXP '^#[0-9A-Fa-f]{6}$'),
  CONSTRAINT ck_empresas_color2   CHECK (color_secundario REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Dominios de correo de cada empresa (una empresa puede tener más de uno).
-- Al iniciar sesión, la parte después de @ indica a qué empresa pertenece el usuario.
CREATE TABLE empresa_dominios (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  dominio     VARCHAR(100)  COLLATE utf8mb4_bin NOT NULL,     -- sin @, en minúsculas: epsel.com.pe
  PRIMARY KEY (id),
  CONSTRAINT uq_dominios_dominio UNIQUE (dominio),              -- un dominio = una sola empresa
  CONSTRAINT ck_dominios_formato CHECK (dominio REGEXP '^[a-z0-9.-]+\\.[a-z]{2,}$'),
  CONSTRAINT fk_dominios_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Áreas de cada empresa (Administración de EPSEL no es la misma que la de Agrofutura)
CREATE TABLE areas (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  nombre      VARCHAR(60)   NOT NULL,
  activo      TINYINT(1)    NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  CONSTRAINT uq_areas_empresa_nombre UNIQUE (empresa_id, nombre),
  CONSTRAINT uq_areas_id_empresa     UNIQUE (id, empresa_id),      -- permite la FK compuesta
  CONSTRAINT fk_areas_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Usuarios del sistema (requisito: tabla users con campo rol y estado activo/inactivo).
-- Cada usuario pertenece a UNA empresa; su correo debe usar un dominio de esa empresa (trigger).
-- El Administrador lo es solo de su empresa.
CREATE TABLE users (
  id             INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id     INT UNSIGNED  NOT NULL,
  area_id        INT UNSIGNED  NULL,
  nombre         VARCHAR(100)  NOT NULL,
  correo         VARCHAR(100)  NOT NULL,
  password_hash  CHAR(60)      NOT NULL,                         -- hash bcrypt, nunca la contraseña
  rol            ENUM('Administrador','Técnico','Solicitante') NOT NULL DEFAULT 'Solicitante',
  activo         TINYINT(1)    NOT NULL DEFAULT 1,
  ultimo_acceso  DATETIME      NULL,
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_users_correo  UNIQUE (correo),
  CONSTRAINT ck_users_nombre  CHECK (CHAR_LENGTH(TRIM(nombre)) >= 3),
  CONSTRAINT ck_users_correo  CHECK (correo REGEXP '^[^@[:space:]]+@[^@[:space:]]+\\.[a-zA-Z]{2,}$'),
  CONSTRAINT ck_users_bcrypt  CHECK (password_hash REGEXP '^\\$2[aby]\\$[0-9]{2}\\$.{53}$'),
  CONSTRAINT fk_users_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  -- el área debe pertenecer a la misma empresa del usuario
  CONSTRAINT fk_users_area    FOREIGN KEY (area_id, empresa_id) REFERENCES areas (id, empresa_id),
  INDEX idx_users_empresa_rol (empresa_id, rol, activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tokens JWT invalidados al cerrar sesión (lista negra)
CREATE TABLE tokens_revocados (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  jti         CHAR(36)      NOT NULL,                            -- identificador único del token
  usuario_id  INT UNSIGNED  NULL,
  expira_en   DATETIME      NULL,                                -- desde aquí ya se puede borrar
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_tokens_jti UNIQUE (jti),
  CONSTRAINT fk_tokens_usuario FOREIGN KEY (usuario_id) REFERENCES users (id) ON DELETE CASCADE,
  INDEX idx_tokens_expira (expira_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MÓDULO 2 — Tickets y evidencias  (+ MÓDULO 4: plazo SLA por prioridad)
-- =====================================================================

-- Catálogos comunes a las 6 empresas
CREATE TABLE categorias (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  nombre      VARCHAR(60)   NOT NULL,
  descripcion VARCHAR(200)  NULL,
  activo      TINYINT(1)    NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  CONSTRAINT uq_categorias_nombre UNIQUE (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Alta 4 h, Media 24 h, Baja 72 h
CREATE TABLE prioridades (
  id          TINYINT UNSIGNED NOT NULL,
  nombre      VARCHAR(10)   NOT NULL,
  sla_horas   SMALLINT UNSIGNED NOT NULL,                        -- tiempo máximo de resolución
  nivel       TINYINT UNSIGNED  NOT NULL,                        -- 3 = más urgente (para ordenar)
  PRIMARY KEY (id),
  CONSTRAINT uq_prioridades_nombre UNIQUE (nombre),
  CONSTRAINT ck_prioridades_sla    CHECK (sla_horas > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tickets (
  id                INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id        INT UNSIGNED  NOT NULL,                      -- la toma el trigger del solicitante
  numero            INT UNSIGNED  NOT NULL,                      -- correlativo por empresa (trigger)
  area_id           INT UNSIGNED  NULL,
  solicitante_id    INT UNSIGNED  NOT NULL,                      -- solicitante automático (usuario en sesión)
  tecnico_id        INT UNSIGNED  NULL,
  categoria_id      INT UNSIGNED  NOT NULL,
  prioridad_id      TINYINT UNSIGNED NOT NULL,
  asunto            VARCHAR(150)  NOT NULL,
  descripcion       TEXT          NOT NULL,
  estado            ENUM('Abierto','En proceso','Resuelto','Cerrado') NOT NULL DEFAULT 'Abierto',
  fecha_limite      DATETIME      NULL,                          -- created_at + sla_horas (trigger)
  fecha_resolucion  DATETIME      NULL,
  fecha_cierre      DATETIME      NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_tickets_empresa_numero UNIQUE (empresa_id, numero),   -- código visible: PREFIJO-0001
  CONSTRAINT ck_tickets_asunto      CHECK (CHAR_LENGTH(TRIM(asunto)) >= 5),
  CONSTRAINT ck_tickets_descripcion CHECK (CHAR_LENGTH(TRIM(descripcion)) >= 10),
  CONSTRAINT fk_tickets_empresa     FOREIGN KEY (empresa_id)        REFERENCES empresas (id),
  CONSTRAINT fk_tickets_area        FOREIGN KEY (area_id, empresa_id) REFERENCES areas (id, empresa_id),
  CONSTRAINT fk_tickets_solicitante FOREIGN KEY (solicitante_id)    REFERENCES users (id),
  CONSTRAINT fk_tickets_tecnico     FOREIGN KEY (tecnico_id)        REFERENCES users (id),
  CONSTRAINT fk_tickets_categoria   FOREIGN KEY (categoria_id)      REFERENCES categorias (id),
  CONSTRAINT fk_tickets_prioridad   FOREIGN KEY (prioridad_id)      REFERENCES prioridades (id),
  INDEX idx_tickets_empresa_estado  (empresa_id, estado),
  INDEX idx_tickets_empresa_fecha   (empresa_id, created_at),
  INDEX idx_tickets_tecnico_estado  (tecnico_id, estado),
  INDEX idx_tickets_fecha_limite    (fecha_limite)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hasta 3 fotos por ticket (orden 1, 2 o 3 y único por ticket). Solo imágenes.
CREATE TABLE ticket_evidencias (
  id               INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  ticket_id        INT UNSIGNED  NOT NULL,
  orden            TINYINT UNSIGNED NOT NULL,
  nombre_original  VARCHAR(255)  NOT NULL,                       -- como lo subió el usuario
  nombre_archivo   VARCHAR(100)  NOT NULL,                       -- nombre seguro guardado en /uploads
  ruta             VARCHAR(255)  NOT NULL,                       -- p. ej. uploads/epsel/12/3f2a....jpg
  mime_type        ENUM('image/jpeg','image/png','image/webp') NOT NULL,
  tamano_bytes     INT UNSIGNED  NOT NULL,
  subido_por       INT UNSIGNED  NOT NULL,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_evidencias_ticket_orden UNIQUE (ticket_id, orden),
  CONSTRAINT uq_evidencias_archivo      UNIQUE (nombre_archivo),
  CONSTRAINT ck_evidencias_orden        CHECK (orden BETWEEN 1 AND 3),
  CONSTRAINT ck_evidencias_tamano       CHECK (tamano_bytes BETWEEN 1 AND 5242880),   -- máx. 5 MB
  CONSTRAINT fk_evidencias_ticket  FOREIGN KEY (ticket_id)  REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_evidencias_usuario FOREIGN KEY (subido_por) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MÓDULO 3 — Historial: asignaciones, cambios de estado y comentarios
-- =====================================================================

CREATE TABLE ticket_historial (
  id                   INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  ticket_id            INT UNSIGNED  NOT NULL,
  usuario_id           INT UNSIGNED  NOT NULL,                   -- quién hizo el cambio
  tipo                 ENUM('CREACION','ASIGNACION','CAMBIO_ESTADO','COMENTARIO') NOT NULL,
  estado_anterior      ENUM('Abierto','En proceso','Resuelto','Cerrado') NULL,
  estado_nuevo         ENUM('Abierto','En proceso','Resuelto','Cerrado') NULL,
  tecnico_anterior_id  INT UNSIGNED  NULL,
  tecnico_nuevo_id     INT UNSIGNED  NULL,
  comentario           TEXT          NOT NULL,                   -- texto obligatorio
  created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- timestamp del evento
  PRIMARY KEY (id),
  CONSTRAINT ck_historial_comentario CHECK (CHAR_LENGTH(TRIM(comentario)) > 0),
  CONSTRAINT ck_historial_estado     CHECK (tipo <> 'CAMBIO_ESTADO'
                                            OR (estado_anterior IS NOT NULL AND estado_nuevo IS NOT NULL
                                                AND estado_anterior <> estado_nuevo)),
  CONSTRAINT ck_historial_asignacion CHECK (tipo <> 'ASIGNACION' OR tecnico_nuevo_id IS NOT NULL),
  CONSTRAINT fk_historial_ticket   FOREIGN KEY (ticket_id)           REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_historial_usuario  FOREIGN KEY (usuario_id)          REFERENCES users (id),
  CONSTRAINT fk_historial_tec_ant  FOREIGN KEY (tecnico_anterior_id) REFERENCES users (id),
  CONSTRAINT fk_historial_tec_new  FOREIGN KEY (tecnico_nuevo_id)    REFERENCES users (id),
  INDEX idx_historial_ticket_fecha (ticket_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MÓDULO 5 — Notificaciones internas
-- =====================================================================

CREATE TABLE notificaciones (
  id                 INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  usuario_id         INT UNSIGNED  NOT NULL,                     -- destinatario
  tipo               ENUM('NUEVO_TICKET','ASIGNACION','CAMBIO_ESTADO','COMENTARIO','SLA') NOT NULL,
  referencia_ticket  INT UNSIGNED  NULL,
  titulo             VARCHAR(150)  NOT NULL,
  mensaje            VARCHAR(255)  NULL,
  leido              TINYINT(1)    NOT NULL DEFAULT 0,
  leido_at           DATETIME      NULL,
  created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_notif_usuario FOREIGN KEY (usuario_id)        REFERENCES users (id)   ON DELETE CASCADE,
  CONSTRAINT fk_notif_ticket  FOREIGN KEY (referencia_ticket) REFERENCES tickets (id) ON DELETE CASCADE,
  INDEX idx_notif_usuario_leido (usuario_id, leido, created_at)  -- contador de la campana
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- =====================================================================
--  VISTAS
-- =====================================================================

-- Módulo 1: datos del usuario + identidad de su empresa (login y cabecera)
CREATE VIEW v_usuarios_sesion AS
SELECT u.id,
       u.nombre,
       u.correo,
       u.password_hash,
       u.rol,
       u.activo,
       u.area_id,
       a.nombre            AS area,
       u.empresa_id,
       e.codigo            AS empresa_codigo,
       e.nombre            AS empresa,
       e.titulo_sistema,
       e.color_primario,
       e.color_secundario,
       e.logo_url,
       e.activo            AS empresa_activa
  FROM users u
  JOIN empresas e    ON e.id = u.empresa_id
  LEFT JOIN areas a  ON a.id = u.area_id;

-- Módulos 2, 4 y 6: listado de tickets con SLA, semáforo y urgencia (filtrar SIEMPRE por empresa_id)
--   semaforo:  verde (< 75 % del plazo) | amarillo (>= 75 %) | rojo (vencido)
--              cumplido / incumplido cuando ya se resolvió
--   urgencia:  3 rojo, 2 amarillo, 1 verde, 0 resuelto/cerrado  -> ORDER BY urgencia DESC
CREATE VIEW v_tickets AS
SELECT x.*,
       CASE x.semaforo WHEN 'rojo' THEN 3 WHEN 'amarillo' THEN 2 WHEN 'verde' THEN 1 ELSE 0 END AS urgencia
FROM (
  SELECT t.id,
         CONCAT(e.prefijo_ticket, '-', LPAD(t.numero, 4, '0')) AS codigo,
         t.numero,
         t.asunto,
         t.descripcion,
         t.estado,
         t.empresa_id,
         e.nombre                           AS empresa,
         t.area_id,
         a.nombre                           AS area,
         t.categoria_id,
         c.nombre                           AS categoria,
         t.prioridad_id,
         p.nombre                           AS prioridad,
         p.nivel                            AS prioridad_nivel,
         p.sla_horas,
         t.solicitante_id,
         s.nombre                           AS solicitante,
         t.tecnico_id,
         COALESCE(tec.nombre, 'Sin asignar') AS tecnico,
         t.created_at,
         t.fecha_limite,
         t.fecha_resolucion,
         t.fecha_cierre,
         TIMESTAMPDIFF(MINUTE, t.created_at, COALESCE(t.fecha_resolucion, t.fecha_cierre, NOW())) AS minutos_transcurridos,
         IF(t.estado IN ('Resuelto', 'Cerrado'), NULL,
            TIMESTAMPDIFF(MINUTE, NOW(), t.fecha_limite)) AS minutos_restantes,
         ROUND(100 * TIMESTAMPDIFF(MINUTE, t.created_at, COALESCE(t.fecha_resolucion, t.fecha_cierre, NOW()))
                   / (p.sla_horas * 60), 1) AS porcentaje_sla,
         CASE
           WHEN t.estado IN ('Resuelto', 'Cerrado') THEN
             IF(COALESCE(t.fecha_resolucion, t.fecha_cierre) <= t.fecha_limite, 'cumplido', 'incumplido')
           WHEN NOW() > t.fecha_limite THEN 'rojo'
           WHEN TIMESTAMPDIFF(MINUTE, t.created_at, NOW()) >= p.sla_horas * 60 * 0.75 THEN 'amarillo'
           ELSE 'verde'
         END                                AS semaforo,
         (SELECT ev.ruta FROM ticket_evidencias ev
           WHERE ev.ticket_id = t.id ORDER BY ev.orden LIMIT 1)       AS miniatura,
         (SELECT COUNT(*) FROM ticket_evidencias ev WHERE ev.ticket_id = t.id) AS total_evidencias
    FROM tickets t
    JOIN empresas    e   ON e.id = t.empresa_id
    LEFT JOIN areas  a   ON a.id = t.area_id
    JOIN categorias  c   ON c.id = t.categoria_id
    JOIN prioridades p   ON p.id = t.prioridad_id
    JOIN users       s   ON s.id = t.solicitante_id
    LEFT JOIN users  tec ON tec.id = t.tecnico_id
) AS x;

-- Módulo 3: línea de tiempo del detalle del ticket
CREATE VIEW v_ticket_timeline AS
SELECT h.id,
       h.ticket_id,
       t.empresa_id,
       h.tipo,
       h.estado_anterior,
       h.estado_nuevo,
       ta.nombre AS tecnico_anterior,
       tn.nombre AS tecnico_nuevo,
       h.comentario,
       h.usuario_id,
       u.nombre  AS usuario,
       u.rol     AS usuario_rol,
       h.created_at,
       TIMESTAMPDIFF(MINUTE, h.created_at, NOW()) AS minutos_desde   -- para "hace 3 h 10 min"
  FROM ticket_historial h
  JOIN tickets t     ON t.id  = h.ticket_id
  JOIN users u       ON u.id  = h.usuario_id
  LEFT JOIN users ta ON ta.id = h.tecnico_anterior_id
  LEFT JOIN users tn ON tn.id = h.tecnico_nuevo_id;

-- Módulo 5: contador de la campana
CREATE VIEW v_notificaciones_pendientes AS
SELECT usuario_id, COUNT(*) AS no_leidas
  FROM notificaciones
 WHERE leido = 0
 GROUP BY usuario_id;

-- Módulo 6: resumen por empresa, área, estado, prioridad y categoría
CREATE VIEW v_dashboard_resumen AS
SELECT t.empresa_id,
       t.area_id,
       a.nombre    AS area,
       t.estado,
       p.nombre    AS prioridad,
       c.nombre    AS categoria,
       DATE(t.created_at) AS fecha,
       COUNT(*)    AS total
  FROM tickets t
  LEFT JOIN areas a  ON a.id = t.area_id
  JOIN prioridades p ON p.id = t.prioridad_id
  JOIN categorias c  ON c.id = t.categoria_id
 GROUP BY t.empresa_id, t.area_id, a.nombre, t.estado, p.nombre, c.nombre, DATE(t.created_at);

-- Módulo 6: tabla "Por responsable" de cada empresa
CREATE VIEW v_dashboard_responsables AS
SELECT t.empresa_id,
       t.tecnico_id,
       COALESCE(u.nombre, 'Sin asignar')                         AS tecnico,
       COUNT(*)                                                 AS asignados,
       SUM(t.estado = 'En proceso')                             AS en_proceso,
       SUM(t.estado IN ('Resuelto', 'Cerrado'))                 AS resueltos,
       ROUND(100 * SUM(t.estado IN ('Resuelto', 'Cerrado')
                       AND COALESCE(t.fecha_resolucion, t.fecha_cierre) <= t.fecha_limite)
                 / NULLIF(SUM(t.estado IN ('Resuelto', 'Cerrado')), 0), 0) AS porcentaje_a_tiempo
  FROM tickets t
  LEFT JOIN users u ON u.id = t.tecnico_id
 GROUP BY t.empresa_id, t.tecnico_id, u.nombre;

-- =====================================================================
--  DATOS INICIALES
--  ⚠ Dominios, títulos y colores son DE EJEMPLO: cada compañero debe
--    reemplazarlos por los de su empresa (tablas empresas y empresa_dominios).
--  Contraseña de todos los usuarios de ejemplo: Clave123 (hash bcrypt)
-- =====================================================================

INSERT INTO empresas (id, codigo, nombre, prefijo_ticket, titulo_sistema, color_primario, color_secundario, logo_url) VALUES
  (1, 'grupo-mm', 'Grupo M&M', 'GMM', 'Mesa de Ayuda Grupo M&M', '#3D4A8A', '#DCE0F5', '/static/img/logos/grupo-mm.png'),
  (2, 'epsel', 'EPSEL', 'EPS', 'Soporte TI EPSEL', '#0077B6', '#D6EEF8', '/static/img/logos/epsel.png'),
  (3, 'robotic-air', 'Robotic Air Systems', 'RAS', 'Help Desk Robotic Air', '#374151', '#E5E7EB', '/static/img/logos/robotic-air.png'),
  (4, 'angel-divino', 'Ángel Divino Bus', 'ADB', 'Soporte TI Ángel Divino Bus', '#B91C1C', '#FBE4E4', '/static/img/logos/angel-divino.png'),
  (5, 'agrofutura', 'Agrofutura', 'AGF', 'Mesa de Ayuda Agrofutura', '#2D6A4F', '#DCF0E5', '/static/img/logos/agrofutura.png'),
  (6, 'atlantica', 'Atlántica', 'ATL', 'Soporte TI Atlántica', '#0E7C86', '#D5F0F2', '/static/img/logos/atlantica.png');

INSERT INTO empresa_dominios (empresa_id, dominio) VALUES
  (1, 'grupomm.com.pe'),
  (2, 'epsel.com.pe'),
  (3, 'roboticair.com.pe'),
  (4, 'angeldivinobus.com.pe'),
  (5, 'agrofutura.com.pe'),
  (6, 'atlantica.com.pe');

-- Las mismas 7 áreas para cada empresa
INSERT INTO areas (id, empresa_id, nombre) VALUES
  (1, 1, 'TI'),
  (2, 1, 'Administración'),
  (3, 1, 'Contabilidad'),
  (4, 1, 'Recursos Humanos'),
  (5, 1, 'Operaciones'),
  (6, 1, 'Ventas'),
  (7, 1, 'Logística'),
  (8, 2, 'TI'),
  (9, 2, 'Administración'),
  (10, 2, 'Contabilidad'),
  (11, 2, 'Recursos Humanos'),
  (12, 2, 'Operaciones'),
  (13, 2, 'Ventas'),
  (14, 2, 'Logística'),
  (15, 3, 'TI'),
  (16, 3, 'Administración'),
  (17, 3, 'Contabilidad'),
  (18, 3, 'Recursos Humanos'),
  (19, 3, 'Operaciones'),
  (20, 3, 'Ventas'),
  (21, 3, 'Logística'),
  (22, 4, 'TI'),
  (23, 4, 'Administración'),
  (24, 4, 'Contabilidad'),
  (25, 4, 'Recursos Humanos'),
  (26, 4, 'Operaciones'),
  (27, 4, 'Ventas'),
  (28, 4, 'Logística'),
  (29, 5, 'TI'),
  (30, 5, 'Administración'),
  (31, 5, 'Contabilidad'),
  (32, 5, 'Recursos Humanos'),
  (33, 5, 'Operaciones'),
  (34, 5, 'Ventas'),
  (35, 5, 'Logística'),
  (36, 6, 'TI'),
  (37, 6, 'Administración'),
  (38, 6, 'Contabilidad'),
  (39, 6, 'Recursos Humanos'),
  (40, 6, 'Operaciones'),
  (41, 6, 'Ventas'),
  (42, 6, 'Logística');

INSERT INTO categorias (id, nombre, descripcion) VALUES
  (1, 'Hardware', 'Equipos, laptops, monitores y periféricos'),
  (2, 'Software', 'Sistemas, aplicaciones y licencias'),
  (3, 'Red e internet', 'Conectividad, VPN, wifi y cableado'),
  (4, 'Accesos y cuentas', 'Usuarios, contraseñas y permisos'),
  (5, 'Impresoras', 'Impresoras, escáneres y suministros'),
  (6, 'Correo', 'Correo corporativo y calendario');

INSERT INTO prioridades (id, nombre, sla_horas, nivel) VALUES
  (1, 'Alta', 4, 3),
  (2, 'Media', 24, 2),
  (3, 'Baja', 72, 1);

-- 1 administrador, técnicos y solicitantes por empresa (empresa_id lo valida el trigger según el dominio)
INSERT INTO users (id, empresa_id, area_id, nombre, correo, password_hash, rol, activo) VALUES
  (1, 1, 1, 'Juan Pérez', 'juan.perez@grupomm.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (2, 1, 1, 'Luis Ramos', 'luis.ramos@grupomm.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (3, 1, 1, 'Pedro Salazar', 'pedro.salazar@grupomm.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (4, 1, 2, 'Valeria Ríos', 'valeria.rios@grupomm.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (5, 1, 7, 'José García', 'jose.garcia@grupomm.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 0),
  (6, 2, 8, 'Ana Díaz', 'ana.diaz@epsel.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (7, 2, 8, 'Carla Mendoza', 'carla.mendoza@epsel.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (8, 2, 10, 'María Torres', 'maria.torres@epsel.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (9, 2, 9, 'Lucía Fernández', 'lucia.fernandez@epsel.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (10, 3, 15, 'Diego Ruiz', 'diego.ruiz@roboticair.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (11, 3, 15, 'Kevin Chávez', 'kevin.chavez@roboticair.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (12, 3, 19, 'Miguel Torres', 'miguel.torres@roboticair.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (13, 4, 22, 'Patricia Quispe', 'patricia.quispe@angeldivinobus.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (14, 4, 22, 'Renato Vega', 'renato.vega@angeldivinobus.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (15, 4, 23, 'Rosa Villanueva', 'rosa.villanueva@angeldivinobus.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (16, 4, 27, 'Carlos Méndez', 'carlos.mendez@angeldivinobus.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (17, 5, 29, 'Martín Salas', 'martin.salas@agrofutura.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (18, 5, 29, 'Sofía Castillo', 'sofia.castillo@agrofutura.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (19, 5, 35, 'Jorge Paredes', 'jorge.paredes@agrofutura.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (20, 6, 36, 'Elena Rojas', 'elena.rojas@atlantica.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Administrador', 1),
  (21, 6, 36, 'Andrés León', 'andres.leon@atlantica.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Técnico', 1),
  (22, 6, 41, 'Lucía Campos', 'lucia.campos@atlantica.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1),
  (23, 6, 39, 'Ana Torres', 'ana.torres@atlantica.com.pe', '$2b$12$Yr1IiIXp.4FEnmCoHAE2Fu2kty/.So1kd.Qkz2qhXnUZCw3eowkXC', 'Solicitante', 1);

-- Tickets de ejemplo. Sin triggers, se insertan con TODOS los datos ya calculados:
--   empresa_id y area_id = los del solicitante, numero = correlativo por empresa,
--   fecha_limite = created_at + horas SLA de la prioridad (Alta 4, Media 24, Baja 72).
INSERT INTO tickets (id, empresa_id, numero, area_id, solicitante_id, tecnico_id, categoria_id, prioridad_id,
                     asunto, descripcion, estado, created_at, fecha_limite, fecha_resolucion, fecha_cierre) VALUES
  (1, 4, 1, 23, 15, 14, 4, 3, 'Cambio de contraseña de correo', 'Necesito restablecer la contraseña de mi correo corporativo, ya no recuerdo la actual.', 'Cerrado', NOW() - INTERVAL 4320 MINUTE, NOW() - INTERVAL 4320 MINUTE + INTERVAL 72 HOUR, NOW() - INTERVAL 4020 MINUTE, NOW() - INTERVAL 3000 MINUTE),
  (2, 1, 1, 2, 4, 2, 1, 2, 'Proyector de sala de reuniones no detecta laptop', 'El proyector de la sala principal no detecta ninguna laptop por HDMI.', 'Resuelto', NOW() - INTERVAL 3000 MINUTE, NOW() - INTERVAL 3000 MINUTE + INTERVAL 24 HOUR, NOW() - INTERVAL 2500 MINUTE, NULL),
  (3, 5, 1, 35, 19, 18, 1, 2, 'Monitor con líneas en pantalla', 'El monitor de la caja 2 muestra líneas verticales de colores desde esta mañana.', 'Resuelto', NOW() - INTERVAL 2880 MINUTE, NOW() - INTERVAL 2880 MINUTE + INTERVAL 24 HOUR, NOW() - INTERVAL 2280 MINUTE, NULL),
  (4, 3, 1, 19, 12, 11, 6, 3, 'Correo no sincroniza en el celular', 'El correo del celular dejó de sincronizar desde ayer, en la laptop sí funciona.', 'En proceso', NOW() - INTERVAL 1440 MINUTE, NOW() - INTERVAL 1440 MINUTE + INTERVAL 72 HOUR, NULL, NULL),
  (5, 6, 1, 41, 22, 21, 1, 2, 'Laptop no enciende', 'La laptop del área de ventas no enciende, el indicador de carga parpadea en naranja.', 'Abierto', NOW() - INTERVAL 1260 MINUTE, NOW() - INTERVAL 1260 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (6, 6, 2, 41, 22, 21, 4, 3, 'Alta de usuario en ERP', 'Se incorporó una nueva asistente de ventas y necesita usuario en el ERP con perfil de consulta.', 'Abierto', NOW() - INTERVAL 830 MINUTE, NOW() - INTERVAL 830 MINUTE + INTERVAL 72 HOUR, NULL, NULL),
  (7, 2, 1, 10, 8, 7, 2, 2, 'Sistema comercial muy lento', 'Desde el lunes el sistema comercial tarda más de un minuto en abrir cada recibo.', 'En proceso', NOW() - INTERVAL 600 MINUTE, NOW() - INTERVAL 600 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (8, 1, 2, 2, 4, 3, 2, 2, 'Licencia de Office vencida', 'Al abrir Excel aparece el mensaje de producto sin licencia y no deja guardar.', 'En proceso', NOW() - INTERVAL 400 MINUTE, NOW() - INTERVAL 400 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (9, 4, 2, 27, 16, NULL, 5, 2, 'Impresora de despacho sin tóner', 'La impresora del área de despacho indica tóner agotado y no imprime las guías.', 'Abierto', NOW() - INTERVAL 300 MINUTE, NOW() - INTERVAL 300 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (10, 4, 3, 23, 15, 14, 2, 1, 'Servidor de facturación caído', 'Desde las 8:00 a. m. no se pueden emitir boletas ni facturas en las tres oficinas. El sistema muestra "No se puede conectar con el servidor".', 'En proceso', NOW() - INTERVAL 280 MINUTE, NOW() - INTERVAL 280 MINUTE + INTERVAL 4 HOUR, NULL, NULL),
  (11, 5, 2, 35, 19, 18, 3, 1, 'VPN no conecta desde almacén', 'Desde la computadora del almacén la VPN muestra error de certificado y no conecta.', 'En proceso', NOW() - INTERVAL 190 MINUTE, NOW() - INTERVAL 190 MINUTE + INTERVAL 4 HOUR, NULL, NULL),
  (12, 2, 2, 9, 9, NULL, 4, 3, 'Acceso a carpeta compartida', 'Necesito permiso de lectura a la carpeta compartida de Contabilidad.', 'Abierto', NOW() - INTERVAL 120 MINUTE, NOW() - INTERVAL 120 MINUTE + INTERVAL 72 HOUR, NULL, NULL);

-- Correlativo de cada empresa = último número usado
UPDATE empresas e SET e.ultimo_ticket = (SELECT COALESCE(MAX(t.numero), 0) FROM tickets t WHERE t.empresa_id = e.id);

-- Primer registro del historial de cada ticket (antes lo hacía trg_tickets_despues_insertar)
INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_nuevo, comentario, created_at)
SELECT id, solicitante_id, 'CREACION', 'Abierto', 'Ticket registrado.', created_at FROM tickets ORDER BY id;

-- Historial de ejemplo
INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, tecnico_anterior_id, tecnico_nuevo_id, comentario, created_at) VALUES
  (1, 13, 'ASIGNACION', NULL, NULL, NULL, 14, 'Gestión de accesos de correo.', NOW() - INTERVAL 4295 MINUTE),
  (1, 14, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Validando la identidad con su jefe.', NOW() - INTERVAL 4260 MINUTE),
  (1, 14, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Contraseña restablecida y enviada por canal seguro.', NOW() - INTERVAL 4020 MINUTE),
  (1, 15, 'CAMBIO_ESTADO', 'Resuelto', 'Cerrado', NULL, NULL, 'Ya pude ingresar, gracias.', NOW() - INTERVAL 3000 MINUTE),
  (2, 1, 'ASIGNACION', NULL, NULL, NULL, 2, 'Revisión del proyector.', NOW() - INTERVAL 2975 MINUTE),
  (2, 2, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se probó con dos laptops y otro cable.', NOW() - INTERVAL 2940 MINUTE),
  (3, 17, 'ASIGNACION', NULL, NULL, NULL, 18, 'Revisión física del equipo.', NOW() - INTERVAL 2855 MINUTE),
  (3, 18, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se probó con otro cable HDMI, el problema persiste.', NOW() - INTERVAL 2820 MINUTE),
  (2, 2, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Se actualizó el firmware del proyector.', NOW() - INTERVAL 2500 MINUTE),
  (3, 18, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Se reemplazó el monitor por uno de reserva.', NOW() - INTERVAL 2280 MINUTE),
  (4, 10, 'ASIGNACION', NULL, NULL, NULL, 11, 'Configuración de correo móvil.', NOW() - INTERVAL 1415 MINUTE),
  (4, 11, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se pidió al usuario reinstalar el perfil de correo.', NOW() - INTERVAL 1380 MINUTE),
  (5, 20, 'ASIGNACION', NULL, NULL, NULL, 21, 'Revisar fuente de poder.', NOW() - INTERVAL 1235 MINUTE),
  (6, 20, 'ASIGNACION', NULL, NULL, NULL, 21, 'Asignado por disponibilidad.', NOW() - INTERVAL 805 MINUTE),
  (7, 6, 'ASIGNACION', NULL, NULL, NULL, 7, 'Revisar rendimiento del servidor comercial.', NOW() - INTERVAL 575 MINUTE),
  (7, 7, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se encontró la base de datos sin mantenimiento, programando reindexación.', NOW() - INTERVAL 540 MINUTE),
  (8, 1, 'ASIGNACION', NULL, NULL, NULL, 3, 'Gestión de licencias.', NOW() - INTERVAL 375 MINUTE),
  (5, 21, 'COMENTARIO', NULL, NULL, NULL, NULL, '¿Puedes enviar una foto del indicador de carga?', NOW() - INTERVAL 360 MINUTE),
  (8, 3, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Reasignando una licencia libre del contrato corporativo.', NOW() - INTERVAL 340 MINUTE),
  (10, 13, 'ASIGNACION', NULL, NULL, NULL, 14, 'Renato es responsable de los servidores.', NOW() - INTERVAL 255 MINUTE),
  (10, 14, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Revisando los registros del servidor. El servicio se detuvo después de la actualización de anoche.', NOW() - INTERVAL 220 MINUTE),
  (11, 17, 'ASIGNACION', NULL, NULL, NULL, 18, 'Asignado al área de redes.', NOW() - INTERVAL 165 MINUTE),
  (11, 18, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Verificando certificados del cliente VPN en el equipo del almacén.', NOW() - INTERVAL 130 MINUTE);


-- Notificaciones de ejemplo (antes las generaba trg_historial_notificar)
-- CREACION -> administradores de la empresa del ticket
INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
SELECT u.id, 'NUEVO_TICKET', h.ticket_id, CONCAT('Nuevo ticket ', v.codigo),
       CONCAT(t.asunto, ' · registrado por ', a.nombre), h.created_at
  FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id JOIN v_tickets v ON v.id = t.id
  JOIN users a ON a.id = h.usuario_id
  JOIN users u ON u.empresa_id = t.empresa_id AND u.rol = 'Administrador' AND u.activo = 1 AND u.id <> h.usuario_id
 WHERE h.tipo = 'CREACION' ORDER BY h.id;

-- ASIGNACION -> técnico asignado
INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
SELECT u.id, 'ASIGNACION', h.ticket_id, CONCAT('Se te asignó el ticket ', v.codigo), t.asunto, h.created_at
  FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id JOIN v_tickets v ON v.id = t.id
  JOIN users u ON u.id = h.tecnico_nuevo_id AND u.id <> h.usuario_id AND u.activo = 1
 WHERE h.tipo = 'ASIGNACION' ORDER BY h.id;

-- ASIGNACION -> solicitante
INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
SELECT u.id, 'ASIGNACION', h.ticket_id, CONCAT(v.codigo, ' fue asignado a ', tn.nombre), t.asunto, h.created_at
  FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id JOIN v_tickets v ON v.id = t.id
  JOIN users tn ON tn.id = h.tecnico_nuevo_id
  JOIN users u ON u.id = t.solicitante_id AND u.id <> h.usuario_id AND u.activo = 1
 WHERE h.tipo = 'ASIGNACION' ORDER BY h.id;

-- CAMBIO_ESTADO y COMENTARIO -> solicitante y técnico (menos quien hizo el cambio)
INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at)
SELECT u.id, h.tipo, h.ticket_id,
       IF(h.tipo = 'CAMBIO_ESTADO', CONCAT(v.codigo, ' cambió a ', h.estado_nuevo), CONCAT('Nuevo comentario en ', v.codigo)),
       IF(h.tipo = 'CAMBIO_ESTADO', CONCAT(t.asunto, ' · por ', a.nombre), CONCAT(t.asunto, ' · ', a.nombre)),
       h.created_at
  FROM ticket_historial h JOIN tickets t ON t.id = h.ticket_id JOIN v_tickets v ON v.id = t.id
  JOIN users a ON a.id = h.usuario_id
  JOIN users u ON u.id IN (t.solicitante_id, t.tecnico_id) AND u.id <> h.usuario_id AND u.activo = 1
 WHERE h.tipo IN ('CAMBIO_ESTADO', 'COMENTARIO') ORDER BY h.id;

-- Las notificaciones de más de 1 día ya aparecen como leídas
UPDATE notificaciones SET leido = 1, leido_at = created_at + INTERVAL 1 HOUR WHERE created_at < NOW() - INTERVAL 1 DAY;

-- =====================================================================
--  CONSULTAS DE REFERENCIA PARA EL BACKEND (Flask + PyMySQL)
--  Están comentadas: son ejemplos para usar en run.py con parámetros %s.
--  REGLA DE ORO: el empresa_id SIEMPRE sale del token JWT del usuario,
--  nunca de lo que envía el navegador.
-- =====================================================================

-- ---------- Módulo 1: identificar la empresa por el correo ----------
-- Al escribir el correo (antes de la contraseña) se puede mostrar la identidad de la empresa:
-- SELECT e.id, e.nombre, e.titulo_sistema, e.color_primario, e.color_secundario, e.logo_url
--   FROM empresa_dominios d JOIN empresas e ON e.id = d.empresa_id
--  WHERE d.dominio = SUBSTRING_INDEX(LOWER(%s), '@', -1) AND e.activo = 1;

-- Login: usuario + su empresa en una sola consulta (luego bcrypt.checkpw con password_hash)
-- SELECT * FROM v_usuarios_sesion WHERE correo = LOWER(%s);
--   -> si activo = 0 o empresa_activa = 0, no se permite el ingreso
--   -> el token JWT guarda: sub = id, rol, empresa_id

-- Usuarios de la empresa (el administrador solo ve los suyos)
-- SELECT id, nombre, correo, rol, area, activo FROM v_usuarios_sesion WHERE empresa_id = %s;
-- INSERT INTO users (empresa_id, area_id, nombre, correo, password_hash, rol)
-- VALUES (%s, %s, %s, %s, %s, %s);      -- falla si el dominio del correo no es de esa empresa
-- UPDATE users SET activo = %s WHERE id = %s AND empresa_id = %s;
-- INSERT INTO tokens_revocados (jti, usuario_id, expira_en) VALUES (%s, %s, %s);   -- logout
-- SELECT 1 FROM tokens_revocados WHERE jti = %s;

-- ---------- Módulo 2: tickets y evidencias ----------
-- INSERT INTO tickets (solicitante_id, categoria_id, prioridad_id, asunto, descripcion)
-- VALUES (%s, %s, %s, %s, %s);          -- empresa, área, correlativo y plazo los pone el trigger
-- INSERT INTO ticket_evidencias (ticket_id, orden, nombre_original, nombre_archivo, ruta, mime_type, tamano_bytes, subido_por)
-- VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
-- SELECT * FROM ticket_evidencias WHERE ticket_id = %s ORDER BY orden;

-- ---------- Módulo 3: asignar, cambiar estado, comentar, timeline ----------
-- CALL sp_asignar_ticket(%s, %s, %s, %s);      -- ticket, técnico, administrador, comentario
-- CALL sp_cambiar_estado(%s, %s, %s, %s);      -- ticket, nuevo estado, usuario, comentario
-- CALL sp_agregar_comentario(%s, %s, %s);      -- ticket, usuario, comentario
-- SELECT * FROM v_ticket_timeline WHERE ticket_id = %s AND empresa_id = %s ORDER BY created_at DESC;
-- Técnicos para el selector de asignación:
-- SELECT id, nombre FROM users WHERE empresa_id = %s AND rol = 'Técnico' AND activo = 1;

-- ---------- Módulo 4: listado por urgencia y alerta ----------
-- SELECT * FROM v_tickets WHERE empresa_id = %s ORDER BY urgencia DESC, minutos_restantes;
-- SELECT * FROM v_tickets WHERE empresa_id = %s AND solicitante_id = %s ...;   -- vista del Solicitante
-- SELECT * FROM v_tickets WHERE empresa_id = %s AND tecnico_id = %s ...;       -- vista del Técnico
-- SELECT SUM(semaforo = 'rojo') AS vencidos, SUM(semaforo = 'amarillo') AS por_vencer
--   FROM v_tickets WHERE empresa_id = %s;

-- ---------- Módulo 5: campana de notificaciones ----------
-- SELECT COUNT(*) FROM notificaciones WHERE usuario_id = %s AND leido = 0;
-- SELECT * FROM notificaciones WHERE usuario_id = %s ORDER BY created_at DESC LIMIT 20;
-- UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE id = %s AND usuario_id = %s;     -- una
-- UPDATE notificaciones SET leido = 1, leido_at = NOW() WHERE usuario_id = %s AND leido = 0;   -- todas

-- ---------- Módulo 6: dashboard de la empresa (GROUP BY con filtros) ----------
-- SELECT estado, COUNT(*) AS total FROM tickets
--  WHERE empresa_id = %s AND created_at BETWEEN %s AND %s
--  GROUP BY estado;
-- SELECT p.nombre AS prioridad, COUNT(*) AS total FROM tickets t
--   JOIN prioridades p ON p.id = t.prioridad_id
--  WHERE t.empresa_id = %s AND t.created_at BETWEEN %s AND %s
--  GROUP BY p.nombre, p.nivel ORDER BY p.nivel DESC;
-- SELECT c.nombre AS categoria, COUNT(*) AS total FROM tickets t
--   JOIN categorias c ON c.id = t.categoria_id
--  WHERE t.empresa_id = %s AND t.created_at BETWEEN %s AND %s
--  GROUP BY c.nombre ORDER BY total DESC;
-- SELECT * FROM v_dashboard_responsables WHERE empresa_id = %s ORDER BY asignados DESC;