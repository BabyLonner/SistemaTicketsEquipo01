-- =====================================================================
--  MESA DE AYUDA TI  -  Base de datos v2 (MySQL 8 / MariaDB 10.4+)
--  Un solo sistema para las 6 empresas del grupo (multiempresa).
--
--  COMPATIBLE CON PYTHONANYWHERE:
--    * SIN triggers, SIN procedimientos almacenados y SIN vistas.
--      Todas las reglas (correlativo, fecha limite SLA, historial,
--      notificaciones, dominio del correo...) las hace Python.
--    * Las fechas se guardan en hora de Peru (UTC-5). Por eso la
--      primera linea fija la zona horaria de esta sesion.
--
--  CUIDADO: borra y vuelve a crear todas las tablas (datos incluidos).
--
--  Como importarlo:
--    Local (XAMPP):  phpMyAdmin > crear base mesa_ayuda_ti > Importar
--    PythonAnywhere: consola Bash del proyecto:
--        python inicializar_bd.py
--      o bien:
--        mysql -u USUARIO -h USUARIO.mysql.pythonanywhere-services.com -p 'USUARIO$base' < database/mesa_ayuda_ti.sql
--
--  Contrasena de TODOS los usuarios de ejemplo: Clave123
-- =====================================================================

SET NAMES utf8mb4;
SET time_zone = '-05:00';
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW IF EXISTS v_dashboard_responsables, v_dashboard_resumen, v_notificaciones_pendientes,
                    v_ticket_timeline, v_tickets, v_usuarios_sesion;
DROP TABLE IF EXISTS reportes_generados, mensajes_externos, ticket_tareas, notificaciones, ticket_historial, ticket_evidencias, tickets, equipos,
                     tokens_revocados, users, areas, categorias, prioridades,
                     empresa_dominios, empresas;

SET FOREIGN_KEY_CHECKS = 1;


-- =====================================================================
--  MODULO 1  -  Empresas, dominios, areas, usuarios y tokens
-- =====================================================================

CREATE TABLE empresas (
  id                INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo            VARCHAR(30)   COLLATE utf8mb4_bin NOT NULL,   -- slug: epsel, grupo-mm
  nombre            VARCHAR(80)   NOT NULL,                      -- nombre comercial
  razon_social      VARCHAR(255)  NULL,
  ruc               CHAR(11)      NULL,
  prefijo_ticket    VARCHAR(5)    COLLATE utf8mb4_bin NOT NULL,   -- EPS -> EPS-0001
  titulo_sistema    VARCHAR(80)   NOT NULL,                      -- titulo que ve la empresa
  color_primario    CHAR(7)       NOT NULL,                      -- #RRGGBB botones y acentos
  color_secundario  CHAR(7)       NOT NULL,                      -- #RRGGBB cabecera y fondos suaves
  logo_url          VARCHAR(255)  NULL,                          -- /static/img/logos/<codigo>.png
  ultimo_ticket     INT UNSIGNED  NOT NULL DEFAULT 0,            -- correlativo (lo sube Python)
  activo            TINYINT(1)    NOT NULL DEFAULT 1,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_empresas_codigo   UNIQUE (codigo),
  CONSTRAINT uq_empresas_nombre   UNIQUE (nombre),
  CONSTRAINT uq_empresas_ruc      UNIQUE (ruc),
  CONSTRAINT uq_empresas_prefijo  UNIQUE (prefijo_ticket),
  CONSTRAINT ck_empresas_ruc      CHECK (ruc IS NULL OR ruc REGEXP '^[0-9]{11}$'),
  CONSTRAINT ck_empresas_prefijo  CHECK (prefijo_ticket REGEXP '^[A-Z]{2,5}$'),
  CONSTRAINT ck_empresas_color1   CHECK (color_primario   REGEXP '^#[0-9A-Fa-f]{6}$'),
  CONSTRAINT ck_empresas_color2   CHECK (color_secundario REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Al iniciar sesion, lo que va despues de @ dice a que empresa pertenece el usuario
CREATE TABLE empresa_dominios (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  dominio     VARCHAR(100)  COLLATE utf8mb4_bin NOT NULL,   -- sin @ y en minusculas
  PRIMARY KEY (id),
  CONSTRAINT uq_dominios_dominio UNIQUE (dominio),
  CONSTRAINT fk_dominios_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE areas (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  nombre      VARCHAR(60)   NOT NULL,
  activo      TINYINT(1)    NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  CONSTRAINT uq_areas_empresa_nombre UNIQUE (empresa_id, nombre),
  CONSTRAINT fk_areas_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Superusuario: no pertenece a ninguna empresa (empresa_id NULL), crea y elimina empresas.
-- Administrador: control total de SU empresa (usuarios, asignaciones, reportes).
CREATE TABLE users (
  id             INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id     INT UNSIGNED  NULL,
  area_id        INT UNSIGNED  NULL,
  nombre         VARCHAR(100)  NOT NULL,
  correo         VARCHAR(120)  NOT NULL,
  telefono       VARCHAR(15)   NULL,                          -- MÓDULO 4: WhatsApp del técnico (E.164 sin +, ej. 51987654321)
  password_hash  CHAR(60)      NOT NULL,                      -- bcrypt, nunca texto plano
  rol            ENUM('Superusuario','Administrador','Técnico','Solicitante') NOT NULL DEFAULT 'Solicitante',
  activo         TINYINT(1)    NOT NULL DEFAULT 1,
  ultimo_acceso  DATETIME      NULL,
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_users_correo  UNIQUE (correo),
  CONSTRAINT ck_users_nombre  CHECK (CHAR_LENGTH(TRIM(nombre)) >= 3),
  CONSTRAINT ck_users_empresa CHECK ((rol = 'Superusuario' AND empresa_id IS NULL)
                                  OR (rol <> 'Superusuario' AND empresa_id IS NOT NULL)),
  CONSTRAINT fk_users_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT fk_users_area    FOREIGN KEY (area_id)    REFERENCES areas (id),
  INDEX idx_users_empresa_rol (empresa_id, rol, activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Lista negra de tokens JWT (cierre de sesion)
CREATE TABLE tokens_revocados (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  jti         CHAR(36)      NOT NULL,
  usuario_id  INT UNSIGNED  NULL,
  expira_en   DATETIME      NULL,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_tokens_jti UNIQUE (jti),
  CONSTRAINT fk_tokens_usuario FOREIGN KEY (usuario_id) REFERENCES users (id) ON DELETE CASCADE,
  INDEX idx_tokens_expira (expira_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MODULO 3 (avance 2)  -  Inventario de equipos con etiqueta QR
--  El QR solo lleva una URL con qr_token (aleatorio, no adivinable).
--  Nunca se codifican datos del equipo ni datos personales en el QR.
-- =====================================================================
CREATE TABLE equipos (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id  INT UNSIGNED  NOT NULL,
  area_id     INT UNSIGNED  NULL,
  codigo      VARCHAR(30)   NOT NULL,                     -- código patrimonial: AGF-PC-001
  nombre      VARCHAR(100)  NOT NULL,                     -- "Laptop de contabilidad"
  tipo        ENUM('Laptop','PC de escritorio','Impresora','Monitor','Proyector','Equipo de red','Teléfono','Otro') NOT NULL DEFAULT 'Otro',
  marca       VARCHAR(50)   NULL,
  modelo      VARCHAR(60)   NULL,
  serie       VARCHAR(60)   NULL,
  ubicacion   VARCHAR(120)  NOT NULL,                     -- "Oficina 2, piso 1"
  qr_token    VARCHAR(24)   COLLATE utf8mb4_bin NOT NULL, -- lo genera Python con secrets.token_urlsafe
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MODULO 2 y 4  -  Catalogos, tickets (con fecha limite SLA) y evidencias
-- =====================================================================

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
  id          TINYINT UNSIGNED  NOT NULL,
  nombre      VARCHAR(10)       NOT NULL,
  sla_horas   SMALLINT UNSIGNED NOT NULL,
  nivel       TINYINT UNSIGNED  NOT NULL,     -- 3 = mas urgente
  PRIMARY KEY (id),
  CONSTRAINT uq_prioridades_nombre UNIQUE (nombre),
  CONSTRAINT ck_prioridades_sla    CHECK (sla_horas > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tickets (
  id                INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id        INT UNSIGNED  NOT NULL,
  numero            INT UNSIGNED  NOT NULL,         -- correlativo por empresa
  area_id           INT UNSIGNED  NULL,
  solicitante_id    INT UNSIGNED  NOT NULL,         -- usuario en sesion (automatico)
  tecnico_id        INT UNSIGNED  NULL,
  equipo_id         INT UNSIGNED  NULL,             -- MÓDULO 3 (avance 2): equipo escaneado con QR
  categoria_id      INT UNSIGNED  NOT NULL,
  prioridad_id      TINYINT UNSIGNED NOT NULL,
  asunto            VARCHAR(150)  NOT NULL,
  descripcion       TEXT          NOT NULL,
  estado            ENUM('Abierto','En proceso','Resuelto','Cerrado') NOT NULL DEFAULT 'Abierto',
  fecha_limite      DATETIME      NOT NULL,         -- created_at + sla_horas (Python)
  fecha_resolucion  DATETIME      NULL,
  fecha_cierre      DATETIME      NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_tickets_empresa_numero UNIQUE (empresa_id, numero),
  CONSTRAINT ck_tickets_asunto      CHECK (CHAR_LENGTH(TRIM(asunto)) >= 5),
  CONSTRAINT ck_tickets_descripcion CHECK (CHAR_LENGTH(TRIM(descripcion)) >= 10),
  CONSTRAINT fk_tickets_empresa     FOREIGN KEY (empresa_id)     REFERENCES empresas (id),
  CONSTRAINT fk_tickets_area        FOREIGN KEY (area_id)        REFERENCES areas (id),
  CONSTRAINT fk_tickets_solicitante FOREIGN KEY (solicitante_id) REFERENCES users (id),
  CONSTRAINT fk_tickets_tecnico     FOREIGN KEY (tecnico_id)     REFERENCES users (id),
  CONSTRAINT fk_tickets_equipo      FOREIGN KEY (equipo_id)      REFERENCES equipos (id) ON DELETE SET NULL,
  CONSTRAINT fk_tickets_categoria   FOREIGN KEY (categoria_id)   REFERENCES categorias (id),
  CONSTRAINT fk_tickets_prioridad   FOREIGN KEY (prioridad_id)   REFERENCES prioridades (id),
  INDEX idx_tickets_empresa_estado (empresa_id, estado),
  INDEX idx_tickets_empresa_fecha  (empresa_id, created_at),
  INDEX idx_tickets_tecnico_estado (tecnico_id, estado),
  INDEX idx_tickets_fecha_limite   (fecha_limite)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hasta 3 fotos por ticket (orden 1, 2 o 3). Solo imagenes JPG/PNG/WEBP.
CREATE TABLE ticket_evidencias (
  id               INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  ticket_id        INT UNSIGNED  NOT NULL,
  orden            TINYINT UNSIGNED NOT NULL,
  nombre_original  VARCHAR(255)  NOT NULL,
  nombre_archivo   VARCHAR(100)  NOT NULL,
  ruta             VARCHAR(255)  NOT NULL,          -- uploads/epsel/12/3f2a.jpg
  mime_type        ENUM('image/jpeg','image/png','image/webp') NOT NULL,
  tamano_bytes     INT UNSIGNED  NOT NULL,
  subido_por       INT UNSIGNED  NOT NULL,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_evidencias_ticket_orden UNIQUE (ticket_id, orden),
  CONSTRAINT uq_evidencias_archivo      UNIQUE (nombre_archivo),
  CONSTRAINT ck_evidencias_orden        CHECK (orden BETWEEN 1 AND 3),
  CONSTRAINT ck_evidencias_tamano       CHECK (tamano_bytes BETWEEN 1 AND 5242880),
  CONSTRAINT fk_evidencias_ticket  FOREIGN KEY (ticket_id)  REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_evidencias_usuario FOREIGN KEY (subido_por) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MODULO 3  -  Historial (asignaciones, cambios de estado y comentarios)
-- =====================================================================

CREATE TABLE ticket_historial (
  id                   INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  ticket_id            INT UNSIGNED  NOT NULL,
  usuario_id           INT UNSIGNED  NOT NULL,
  tipo                 ENUM('CREACION','ASIGNACION','CAMBIO_ESTADO','COMENTARIO') NOT NULL,
  estado_anterior      ENUM('Abierto','En proceso','Resuelto','Cerrado') NULL,
  estado_nuevo         ENUM('Abierto','En proceso','Resuelto','Cerrado') NULL,
  tecnico_anterior_id  INT UNSIGNED  NULL,
  tecnico_nuevo_id     INT UNSIGNED  NULL,
  comentario           TEXT          NOT NULL,      -- obligatorio
  created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
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


-- Tareas del ticket (pestaña "Tareas" del detalle): lista de pasos que sigue el técnico
CREATE TABLE ticket_tareas (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  ticket_id       INT UNSIGNED  NOT NULL,
  descripcion     VARCHAR(200)  NOT NULL,
  completada      TINYINT(1)    NOT NULL DEFAULT 0,
  creado_por      INT UNSIGNED  NOT NULL,
  completada_por  INT UNSIGNED  NULL,
  completada_at   DATETIME      NULL,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT ck_tareas_descripcion CHECK (CHAR_LENGTH(TRIM(descripcion)) >= 3),
  CONSTRAINT fk_tareas_ticket  FOREIGN KEY (ticket_id)      REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_tareas_creador FOREIGN KEY (creado_por)     REFERENCES users (id),
  CONSTRAINT fk_tareas_cierre  FOREIGN KEY (completada_por) REFERENCES users (id),
  INDEX idx_tareas_ticket (ticket_id, completada)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MODULO 5  -  Notificaciones internas
-- =====================================================================

CREATE TABLE notificaciones (
  id                 INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  usuario_id         INT UNSIGNED  NOT NULL,      -- destinatario
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
  INDEX idx_notif_usuario_leido (usuario_id, leido, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
--  MODULO 4 (avance 2)  -  Aviso al técnico por WhatsApp / SMS (Vonage)
--  Cada mensaje enviado queda registrado con su estado. El estado se
--  actualiza con el webhook de Vonage (ENVIADO -> ENTREGADO -> LEIDO).
-- =====================================================================
CREATE TABLE mensajes_externos (
  id               INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  empresa_id       INT UNSIGNED  NOT NULL,
  ticket_id        INT UNSIGNED  NULL,                 -- NULL = mensaje de prueba desde Mi Perfil
  tecnico_id       INT UNSIGNED  NOT NULL,             -- destinatario
  enviado_por      INT UNSIGNED  NULL,                 -- quién asignó (NULL = sistema)
  canal            ENUM('WHATSAPP','SMS') NOT NULL DEFAULT 'WHATSAPP',
  motivo           ENUM('ASIGNACION','REASIGNACION','PRUEBA') NOT NULL DEFAULT 'ASIGNACION',
  telefono         VARCHAR(15)   NULL,                 -- número al que se envió (NULL si el técnico no tenía)
  mensaje          VARCHAR(600)  NOT NULL,
  proveedor_id     VARCHAR(64)   NULL,                 -- message_uuid que devuelve Vonage
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  MODULO 8  -  Reportes PDF verificables (codigo QR + hash SHA-256)
-- =====================================================================

CREATE TABLE reportes_generados (
  id             INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo         VARCHAR(32)   COLLATE utf8mb4_bin NOT NULL,     -- va en el QR: /verificar/<codigo>
  empresa_id     INT UNSIGNED  NOT NULL,
  periodo_desde  DATE          NULL,                             -- NULL = desde el inicio
  periodo_hasta  DATE          NULL,                             -- NULL = hasta hoy
  filtros        VARCHAR(500)  NOT NULL,                         -- texto de filtros impreso en el PDF
  total_tickets  INT UNSIGNED  NOT NULL DEFAULT 0,
  hash_sha256    CHAR(64)      NOT NULL,                         -- huella del PDF terminado
  generado_por   INT UNSIGNED  NULL,                             -- NULL = envio automatico
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT uq_reportes_codigo  UNIQUE (codigo),
  CONSTRAINT ck_reportes_hash    CHECK (hash_sha256 REGEXP '^[0-9a-f]{64}$'),
  CONSTRAINT fk_reportes_empresa FOREIGN KEY (empresa_id)   REFERENCES empresas (id) ON DELETE CASCADE,
  CONSTRAINT fk_reportes_usuario FOREIGN KEY (generado_por) REFERENCES users (id)    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
--  DATOS INICIALES
-- =====================================================================

INSERT INTO categorias (id, nombre, descripcion) VALUES
  (1, 'Hardware',          'Equipos, laptops, monitores y perifericos'),
  (2, 'Software',          'Sistemas, aplicaciones y licencias'),
  (3, 'Red e internet',    'Conectividad, VPN, wifi y cableado'),
  (4, 'Accesos y cuentas', 'Usuarios, contrasenas y permisos'),
  (5, 'Impresoras',        'Impresoras, escaneres y suministros'),
  (6, 'Correo',            'Correo corporativo y calendario');

INSERT INTO prioridades (id, nombre, sla_horas, nivel) VALUES
  (1, 'Alta', 4, 3),
  (2, 'Media', 24, 2),
  (3, 'Baja', 72, 1);

-- Las 6 empresas del grupo con su identidad visual
INSERT INTO empresas (id, codigo, nombre, razon_social, prefijo_ticket, titulo_sistema, color_primario, color_secundario, logo_url) VALUES
  (1, 'grupo-mm',     'Grupo M&M',         'M & M Logística y Almacenes S.A.C. / M & M Transporte y Distribución S.A.C. / M & M Servicios Motorizados S.A.C.', 'GMM', 'Mesa de Ayuda Grupo M&M', '#3D4A8A', '#DCE0F5', '/static/img/logos/grupo-mm.png'),
  (2, 'agrofutura',   'Agrofutura',        'Agrofutura Company S.A.C.', 'AGF', 'Mesa de Ayuda Agrofutura',    '#2D6A4F', '#DCF0E5', '/static/img/logos/agrofutura.png'),
  (3, 'epsel',        'EPSEL',             'EPSEL S.A.',                'EPS', 'Soporte TI EPSEL',            '#0077B6', '#D6EEF8', '/static/img/logos/epsel.png'),
  (4, 'provida',      'Clínica Provida',   'Clínica Provida',           'CPV', 'Soporte TI Clínica Provida',  '#0E7C7E', '#D6EDED', NULL),
  (5, 'atlantica',    'Atlántica',         'Atlántica S.A.C.',          'ATL', 'Soporte TI Atlántica',        '#0E7C86', '#D5F0F2', '/static/img/logos/atlantica.png'),
  (6, 'angel-divino', 'Ángel Divino Bus',  'Ángel Divino Bus S.A.C.',   'ADB', 'Soporte TI Ángel Divino Bus', '#B91C1C', '#FBE4E4', '/static/img/logos/angel-divino.png');

INSERT INTO empresa_dominios (empresa_id, dominio) VALUES
  (1, 'grupomm.com.pe'),
  (2, 'agrofutura.com.pe'),
  (3, 'epsel.com.pe'),
  (4, 'clinicaprovida.com.pe'),
  (5, 'atlantica.com.pe'),
  (6, 'angeldivinobus.com.pe');

-- 6 areas por empresa (id = (empresa-1)*6 + n)
INSERT INTO areas (id, empresa_id, nombre) VALUES
  (1,1,'TI'),(2,1,'Administración'),(3,1,'Contabilidad'),(4,1,'Recursos Humanos'),(5,1,'Operaciones'),(6,1,'Logística'),
  (7,2,'TI'),(8,2,'Administración'),(9,2,'Contabilidad'),(10,2,'Recursos Humanos'),(11,2,'Operaciones'),(12,2,'Logística'),
  (13,3,'TI'),(14,3,'Administración'),(15,3,'Contabilidad'),(16,3,'Recursos Humanos'),(17,3,'Operaciones'),(18,3,'Comercial'),
  (19,4,'TI'),(20,4,'Administración'),(21,4,'Contabilidad'),(22,4,'Recursos Humanos'),(23,4,'Admisión'),(24,4,'Farmacia'),
  (25,5,'TI'),(26,5,'Administración'),(27,5,'Contabilidad'),(28,5,'Recursos Humanos'),(29,5,'Operaciones'),(30,5,'Ventas'),
  (31,6,'TI'),(32,6,'Administración'),(33,6,'Contabilidad'),(34,6,'Recursos Humanos'),(35,6,'Operaciones'),(36,6,'Venta de pasajes');

-- Superusuario + administrador (contacto de cada empresa) + tecnicos y solicitantes de ejemplo.
-- Contrasena de todos: Clave123
INSERT INTO users (id, empresa_id, area_id, nombre, correo, password_hash, rol, activo) VALUES
  (1,  NULL, NULL, 'Superusuario del sistema',        'superadmin@mesadeayuda.com.pe',      '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Superusuario', 1),

  (2,  1, 1,  'Victor Toribio Melgarejo Tamara',     'victor.melgarejo@grupomm.com.pe',     '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (3,  1, 1,  'Luis Ramos',                          'luis.ramos@grupomm.com.pe',           '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (4,  1, 1,  'Pedro Salazar',                       'pedro.salazar@grupomm.com.pe',        '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (5,  1, 6,  'Valeria Ríos',                        'valeria.rios@grupomm.com.pe',         '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1),

  (6,  2, 7,  'Christian Llontop Flores',            'christian.llontop@agrofutura.com.pe', '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (7,  2, 7,  'Sofía Castillo',                      'sofia.castillo@agrofutura.com.pe',    '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (8,  2, 12, 'Jorge Paredes',                       'jorge.paredes@agrofutura.com.pe',     '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1),

  (9,  3, 13, 'Sergio James Goicochea Espinosa',     'sergio.goicochea@epsel.com.pe',       '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (10, 3, 13, 'Carla Mendoza',                       'carla.mendoza@epsel.com.pe',          '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (11, 3, 15, 'María Torres',                        'maria.torres@epsel.com.pe',           '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1),

  (12, 4, 19, 'Julio Cesar Salazar Tineo',           'julio.salazar@clinicaprovida.com.pe', '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (13, 4, 19, 'Kevin Chávez',                        'kevin.chavez@clinicaprovida.com.pe',  '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (14, 4, 23, 'Miguel Torres',                       'miguel.torres@clinicaprovida.com.pe', '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1),

  (15, 5, 25, 'Elki Omar Villacorta Silva',          'elki.villacorta@atlantica.com.pe',    '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (16, 5, 25, 'Andrés León',                         'andres.leon@atlantica.com.pe',        '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (17, 5, 30, 'Lucía Campos',                        'lucia.campos@atlantica.com.pe',       '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1),

  (18, 6, 31, 'Hugo Fernando Tantajulca Rimarachin', 'hugo.tantajulca@angeldivinobus.com.pe','$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Administrador', 1),
  (19, 6, 31, 'Renato Vega',                         'renato.vega@angeldivinobus.com.pe',   '$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Técnico', 1),
  (20, 6, 32, 'Rosa Villanueva',                     'rosa.villanueva@angeldivinobus.com.pe','$2b$12$cjutzy2.nwBpj0P8YiRoTen0Tw6EsRcb6Vs674K1Nx19gzSamG..W', 'Solicitante', 1);

-- Tickets de ejemplo (sin triggers: se insertan con todo ya calculado)
--   fecha_limite = created_at + horas de la prioridad (Alta 4, Media 24, Baja 72)
INSERT INTO tickets (id, empresa_id, numero, area_id, solicitante_id, tecnico_id, categoria_id, prioridad_id,
                     asunto, descripcion, estado, created_at, fecha_limite, fecha_resolucion, fecha_cierre) VALUES
  (1, 6, 1, 32, 20, 19, 4, 3, 'Cambio de contraseña de correo', 'Necesito restablecer la contraseña de mi correo corporativo, ya no recuerdo la actual.', 'Cerrado',
      NOW() - INTERVAL 4320 MINUTE, NOW() - INTERVAL 4320 MINUTE + INTERVAL 72 HOUR, NOW() - INTERVAL 4020 MINUTE, NOW() - INTERVAL 3000 MINUTE),
  (2, 1, 1, 6, 5, 3, 1, 2, 'Proyector de sala de reuniones no detecta laptop', 'El proyector de la sala principal no detecta ninguna laptop por HDMI.', 'Resuelto',
      NOW() - INTERVAL 3000 MINUTE, NOW() - INTERVAL 3000 MINUTE + INTERVAL 24 HOUR, NOW() - INTERVAL 2500 MINUTE, NULL),
  (3, 2, 1, 12, 8, 7, 1, 2, 'Monitor con líneas en pantalla', 'El monitor de la caja 2 muestra líneas verticales de colores desde esta mañana.', 'Resuelto',
      NOW() - INTERVAL 2880 MINUTE, NOW() - INTERVAL 2880 MINUTE + INTERVAL 24 HOUR, NOW() - INTERVAL 2280 MINUTE, NULL),
  (4, 4, 1, 23, 14, 13, 6, 3, 'Correo no sincroniza en el celular', 'El correo del celular dejó de sincronizar desde ayer, en la laptop sí funciona.', 'En proceso',
      NOW() - INTERVAL 1440 MINUTE, NOW() - INTERVAL 1440 MINUTE + INTERVAL 72 HOUR, NULL, NULL),
  (5, 5, 1, 30, 17, 16, 1, 2, 'Laptop no enciende', 'La laptop del área de ventas no enciende, el indicador de carga parpadea en naranja.', 'Abierto',
      NOW() - INTERVAL 1260 MINUTE, NOW() - INTERVAL 1260 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (6, 5, 2, 30, 17, 16, 4, 3, 'Alta de usuario en ERP', 'Se incorporó una nueva asistente de ventas y necesita usuario en el ERP con perfil de consulta.', 'Abierto',
      NOW() - INTERVAL 830 MINUTE, NOW() - INTERVAL 830 MINUTE + INTERVAL 72 HOUR, NULL, NULL),
  (7, 3, 1, 15, 11, 10, 2, 2, 'Sistema comercial muy lento', 'Desde el lunes el sistema comercial tarda más de un minuto en abrir cada recibo.', 'En proceso',
      NOW() - INTERVAL 600 MINUTE, NOW() - INTERVAL 600 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (8, 1, 2, 6, 5, 4, 2, 2, 'Licencia de Office vencida', 'Al abrir Excel aparece el mensaje de producto sin licencia y no deja guardar.', 'En proceso',
      NOW() - INTERVAL 400 MINUTE, NOW() - INTERVAL 400 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (9, 6, 2, 32, 20, NULL, 5, 2, 'Impresora de despacho sin tóner', 'La impresora del área de despacho indica tóner agotado y no imprime las guías.', 'Abierto',
      NOW() - INTERVAL 300 MINUTE, NOW() - INTERVAL 300 MINUTE + INTERVAL 24 HOUR, NULL, NULL),
  (10, 6, 3, 32, 20, 19, 2, 1, 'Servidor de facturación caído', 'Desde las 8:00 a. m. no se pueden emitir boletas ni facturas en las tres oficinas de venta de pasajes. El sistema muestra que no se puede conectar con el servidor.', 'En proceso',
      NOW() - INTERVAL 280 MINUTE, NOW() - INTERVAL 280 MINUTE + INTERVAL 4 HOUR, NULL, NULL),
  (11, 2, 2, 12, 8, 7, 3, 1, 'VPN no conecta desde almacén', 'Desde la computadora del almacén la VPN muestra error de certificado y no conecta.', 'En proceso',
      NOW() - INTERVAL 190 MINUTE, NOW() - INTERVAL 190 MINUTE + INTERVAL 4 HOUR, NULL, NULL),
  (12, 3, 2, 15, 11, NULL, 4, 3, 'Acceso a carpeta compartida', 'Necesito permiso de lectura a la carpeta compartida de Contabilidad.', 'Abierto',
      NOW() - INTERVAL 120 MINUTE, NOW() - INTERVAL 120 MINUTE + INTERVAL 72 HOUR, NULL, NULL);

-- MÓDULO 3 (avance 2): equipos de ejemplo con su token de QR
INSERT INTO equipos (id, empresa_id, area_id, codigo, nombre, tipo, marca, modelo, serie, ubicacion, qr_token) VALUES
  (1,  1, 6,  'GMM-PC-001',  'PC de logística',              'PC de escritorio', 'Lenovo', 'ThinkCentre M70',  'MJ0GH21A', 'Almacén central, módulo 1',      'cA-f-GIxyxZPyrQX'),
  (2,  1, 1,  'GMM-PRY-001', 'Proyector sala de reuniones',  'Proyector',        'Epson',  'PowerLite X49',    'X49K7731', 'Sala de reuniones principal',    'rt0wMkMUy-Lxezg3'),
  (3,  2, 12, 'AGF-MON-001', 'Monitor de la caja 2',         'Monitor',          'LG',     '24MK430H',         '304NTAB55', 'Almacén, caja 2',               '0Ox4Wcj-TO3Jxhyx'),
  (4,  2, 12, 'AGF-PC-001',  'PC del almacén',               'PC de escritorio', 'HP',     'ProDesk 400 G7',   'MXL1234ABC', 'Almacén, escritorio de recepción','kdJ8LIBx3sO0He6u'),
  (5,  2, 9,  'AGF-IMP-001', 'Impresora de contabilidad',    'Impresora',        'Epson',  'EcoTank L4260',    'X8HW001122', 'Contabilidad, piso 2',          'sxBbe89tpLGk_hID'),
  (6,  2, 7,  'AGF-LAP-001', 'Laptop de soporte TI',         'Laptop',           'Dell',   'Latitude 3420',    'DL3420TI01', 'Oficina de TI, piso 1',         'wMrp81NFUdfFE7_H'),
  (7,  3, 15, 'EPS-PC-001',  'PC de contabilidad',           'PC de escritorio', 'Dell',   'OptiPlex 3080',    'OPX3080C1', 'Contabilidad, oficina 3',        'dsRFyzpw5mFbxgwh'),
  (8,  3, 18, 'EPS-IMP-001', 'Impresora del área comercial', 'Impresora',        'HP',     'LaserJet M404',    'PHBCK4410', 'Comercial, mostrador',           'daf1XRTOcJ701obd'),
  (9,  4, 23, 'CPV-LAP-001', 'Laptop de admisión',           'Laptop',           'Lenovo', 'IdeaPad 3',        'PF3ADM01',  'Admisión, ventanilla 1',         'wCm78zZ7HS5KiaSg'),
  (10, 4, 24, 'CPV-PC-001',  'PC de farmacia',               'PC de escritorio', 'HP',     'EliteDesk 800',    'MXL77FAR1', 'Farmacia, caja',                 'j-xj0xkYh98SCeyx'),
  (11, 5, 30, 'ATL-LAP-001', 'Laptop de ventas',             'Laptop',           'HP',     'ProBook 440',      '5CD1VEN01', 'Ventas, escritorio 4',           'eOQNEx5t3wNDIdtT'),
  (12, 5, 25, 'ATL-RED-001', 'Switch principal',             'Equipo de red',    'Cisco',  'CBS250-24T',       'PSZ25VENT', 'Cuarto de comunicaciones',       'rgBmlL5fhCFkJKHh'),
  (13, 6, 32, 'ADB-IMP-001', 'Impresora de despacho',        'Impresora',        'Brother','HL-L5100DN',       'U63891K0N', 'Despacho, oficina principal',    'zM7yEZEhTv3N74FB'),
  (14, 6, 36, 'ADB-PC-001',  'PC de venta de pasajes',       'PC de escritorio', 'Lenovo', 'V50s',             'PC1VPAS01', 'Counter de venta de pasajes 1',  'sRj-aM7l5BZJeDkk');

-- Tickets de ejemplo que ya estaban vinculados a un equipo (historial de incidencias)
UPDATE tickets SET equipo_id = 2  WHERE id = 2;
UPDATE tickets SET equipo_id = 3  WHERE id = 3;
UPDATE tickets SET equipo_id = 11 WHERE id = 5;
UPDATE tickets SET equipo_id = 13 WHERE id = 9;
UPDATE tickets SET equipo_id = 4  WHERE id = 11;
UPDATE tickets SET equipo_id = 7  WHERE id = 7;

UPDATE empresas e SET e.ultimo_ticket = (SELECT COALESCE(MAX(t.numero), 0) FROM tickets t WHERE t.empresa_id = e.id);

INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_nuevo, comentario, created_at)
SELECT id, solicitante_id, 'CREACION', 'Abierto', 'Ticket registrado.', created_at FROM tickets ORDER BY id;

INSERT INTO ticket_historial (ticket_id, usuario_id, tipo, estado_anterior, estado_nuevo, tecnico_anterior_id, tecnico_nuevo_id, comentario, created_at) VALUES
  (1, 18, 'ASIGNACION', NULL, NULL, NULL, 19, 'Gestión de accesos de correo.', NOW() - INTERVAL 4295 MINUTE),
  (1, 19, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Validando la identidad con su jefe.', NOW() - INTERVAL 4260 MINUTE),
  (1, 19, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Contraseña restablecida y enviada por canal seguro.', NOW() - INTERVAL 4020 MINUTE),
  (1, 20, 'CAMBIO_ESTADO', 'Resuelto', 'Cerrado', NULL, NULL, 'Ya pude ingresar, gracias.', NOW() - INTERVAL 3000 MINUTE),
  (2, 2, 'ASIGNACION', NULL, NULL, NULL, 3, 'Revisión del proyector.', NOW() - INTERVAL 2975 MINUTE),
  (2, 3, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se probó con dos laptops y otro cable.', NOW() - INTERVAL 2940 MINUTE),
  (2, 3, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Se actualizó el firmware del proyector.', NOW() - INTERVAL 2500 MINUTE),
  (3, 6, 'ASIGNACION', NULL, NULL, NULL, 7, 'Revisión física del equipo.', NOW() - INTERVAL 2855 MINUTE),
  (3, 7, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se probó con otro cable HDMI, el problema persiste.', NOW() - INTERVAL 2820 MINUTE),
  (3, 7, 'CAMBIO_ESTADO', 'En proceso', 'Resuelto', NULL, NULL, 'Se reemplazó el monitor por uno de reserva.', NOW() - INTERVAL 2280 MINUTE),
  (4, 12, 'ASIGNACION', NULL, NULL, NULL, 13, 'Configuración de correo móvil.', NOW() - INTERVAL 1415 MINUTE),
  (4, 13, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Se pidió al usuario reinstalar el perfil de correo.', NOW() - INTERVAL 1380 MINUTE),
  (5, 15, 'ASIGNACION', NULL, NULL, NULL, 16, 'Revisar fuente de poder.', NOW() - INTERVAL 1235 MINUTE),
  (5, 16, 'COMENTARIO', NULL, NULL, NULL, NULL, '¿Puedes enviar una foto del indicador de carga?', NOW() - INTERVAL 360 MINUTE),
  (6, 15, 'ASIGNACION', NULL, NULL, NULL, 16, 'Asignado por disponibilidad.', NOW() - INTERVAL 805 MINUTE),
  (7, 9, 'ASIGNACION', NULL, NULL, NULL, 10, 'Revisar rendimiento del servidor comercial.', NOW() - INTERVAL 575 MINUTE),
  (7, 10, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'La base de datos no tenía mantenimiento, programando reindexación.', NOW() - INTERVAL 540 MINUTE),
  (8, 2, 'ASIGNACION', NULL, NULL, NULL, 4, 'Gestión de licencias.', NOW() - INTERVAL 375 MINUTE),
  (8, 4, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Reasignando una licencia libre del contrato corporativo.', NOW() - INTERVAL 340 MINUTE),
  (10, 18, 'ASIGNACION', NULL, NULL, NULL, 19, 'Renato es responsable de los servidores.', NOW() - INTERVAL 240 MINUTE),
  (10, 19, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Revisando los registros del servidor. El servicio se detuvo después de la actualización de anoche.', NOW() - INTERVAL 190 MINUTE),
  (11, 6, 'ASIGNACION', NULL, NULL, NULL, 7, 'Asignado al área de redes.', NOW() - INTERVAL 165 MINUTE),
  (11, 7, 'CAMBIO_ESTADO', 'Abierto', 'En proceso', NULL, NULL, 'Verificando certificados del cliente VPN en el equipo del almacén.', NOW() - INTERVAL 130 MINUTE);

-- Notificaciones de ejemplo (en el sistema real las genera Python)
INSERT INTO notificaciones (usuario_id, tipo, referencia_ticket, titulo, mensaje, created_at) VALUES
  (19, 'ASIGNACION',    10, 'Se te asignó el ticket ADB-0003', 'Servidor de facturación caído', NOW() - INTERVAL 240 MINUTE),
  (20, 'CAMBIO_ESTADO', 10, 'ADB-0003 cambió a En proceso',    'Servidor de facturación caído', NOW() - INTERVAL 190 MINUTE),
  (18, 'NUEVO_TICKET',   9, 'Nuevo ticket ADB-0002',           'Impresora de despacho sin tóner', NOW() - INTERVAL 300 MINUTE),
  (18, 'NUEVO_TICKET',  10, 'Nuevo ticket ADB-0003',           'Servidor de facturación caído', NOW() - INTERVAL 280 MINUTE),
  (8,  'CAMBIO_ESTADO', 11, 'AGF-0002 cambió a En proceso',    'VPN no conecta desde almacén', NOW() - INTERVAL 130 MINUTE),
  (8,  'CAMBIO_ESTADO',  3, 'AGF-0001 cambió a Resuelto',      'Monitor con líneas en pantalla', NOW() - INTERVAL 2280 MINUTE),
  (7,  'ASIGNACION',    11, 'Se te asignó el ticket AGF-0002', 'VPN no conecta desde almacén', NOW() - INTERVAL 165 MINUTE),
  (17, 'COMENTARIO',     5, 'Nuevo comentario en ATL-0001',    'Laptop no enciende', NOW() - INTERVAL 360 MINUTE),
  (16, 'ASIGNACION',     6, 'Se te asignó el ticket ATL-0002', 'Alta de usuario en ERP', NOW() - INTERVAL 805 MINUTE),
  (9,  'NUEVO_TICKET',  12, 'Nuevo ticket EPS-0002',           'Acceso a carpeta compartida', NOW() - INTERVAL 120 MINUTE),
  (10, 'ASIGNACION',     7, 'Se te asignó el ticket EPS-0001', 'Sistema comercial muy lento', NOW() - INTERVAL 575 MINUTE),
  (3,  'ASIGNACION',     2, 'Se te asignó el ticket GMM-0001', 'Proyector de sala de reuniones no detecta laptop', NOW() - INTERVAL 2975 MINUTE),
  (5,  'CAMBIO_ESTADO',  8, 'GMM-0002 cambió a En proceso',    'Licencia de Office vencida', NOW() - INTERVAL 340 MINUTE),
  (13, 'ASIGNACION',     4, 'Se te asignó el ticket CPV-0001', 'Correo no sincroniza en el celular', NOW() - INTERVAL 1415 MINUTE);

UPDATE notificaciones SET leido = 1, leido_at = created_at + INTERVAL 1 HOUR WHERE created_at < NOW() - INTERVAL 1 DAY;

-- Tareas de ejemplo
INSERT INTO ticket_tareas (ticket_id, descripcion, completada, creado_por, completada_por, completada_at, created_at) VALUES
  (10, 'Revisar los registros del servidor de facturación', 1, 19, 19, NOW() - INTERVAL 150 MINUTE, NOW() - INTERVAL 185 MINUTE),
  (10, 'Revertir la actualización de anoche', 0, 19, NULL, NULL, NOW() - INTERVAL 140 MINUTE),
  (10, 'Validar emisión de boletas en las 3 oficinas', 0, 19, NULL, NULL, NOW() - INTERVAL 140 MINUTE),
  (7,  'Programar reindexación de la base de datos', 0, 10, NULL, NULL, NOW() - INTERVAL 500 MINUTE);

-- Las cuentas de ejemplo se dan por creadas hace mes y medio (para los indicadores "vs. mes anterior")
UPDATE users SET created_at = NOW() - INTERVAL 45 DAY, updated_at = NOW() - INTERVAL 45 DAY;
