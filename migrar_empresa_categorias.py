from db import conexion
# Importa tu aplicación Flask principal (cambia 'run' por el nombre del archivo donde inicializas Flask, ej: 'app')
try:
    from run import app
except ImportError:
    from app import app  # Ajusta según cómo se llame tu archivo principal de arranque

def migrar_empresa_categorias():
    with app.app_context():
        con = conexion()
        try:
            with con.cursor() as cur:
                # 1. Crear la tabla intermedia
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS empresa_categoria_prioridad (
                        id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                        empresa_id INT UNSIGNED NOT NULL,
                        categoria_id INT UNSIGNED NOT NULL,
                        prioridad_id TINYINT UNSIGNED NOT NULL,
                        PRIMARY KEY (id),
                        CONSTRAINT uq_empresa_categoria UNIQUE (empresa_id, categoria_id),
                        CONSTRAINT fk_ecp_empresa FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
                        CONSTRAINT fk_ecp_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE CASCADE,
                        CONSTRAINT fk_ecp_prioridad FOREIGN KEY (prioridad_id) REFERENCES prioridades(id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)
                
                # 2. Insertar configuración por defecto (Prioridad 2: Media)
                cur.execute("""
                    INSERT IGNORE INTO empresa_categoria_prioridad (empresa_id, categoria_id, prioridad_id)
                    SELECT e.id, c.id, 2 
                    FROM empresas e 
                    CROSS JOIN categorias c
                """)
            con.commit()
            print("¡Tabla empresa_categoria_prioridad creada y configurada con éxito!")
        except Exception as e:
            con.rollback()
            print(f"Error durante la migración: {e}")
        finally:
            con.close()

if __name__ == "__main__":
    migrar_empresa_categorias()