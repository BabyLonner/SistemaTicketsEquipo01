from db import conexion

def migrar_categorias():
    con = conexion()
    try:
        with con.cursor() as cur:
            # 1. Verificar si la columna ya existe para evitar errores de duplicidad
            cur.execute("""
                SELECT COUNT(*) as existe 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                  AND TABLE_NAME = 'categorias' 
                  AND COLUMN_NAME = 'prioridad_id'
            """)
            if cur.fetchone()['existe'] > 0:
                print("La columna 'prioridad_id' ya existe. No se requiere migración estructural.")
                return

            print("1. Creando columna prioridad_id en categorias...")
            cur.execute("ALTER TABLE categorias ADD COLUMN prioridad_id TINYINT UNSIGNED NULL")

            print("2. Asignando prioridades a las categorías existentes...")
            # 1: Alta(4h), 2: Media(24h), 3: Baja(72h)
            actualizaciones = [
                (2, 1), # Hardware -> Media
                (2, 2), # Software -> Media
                (1, 3), # Red e internet -> Alta
                (3, 4), # Accesos y cuentas -> Baja
                (3, 5), # Impresoras -> Baja
                (2, 6)  # Correo -> Media
            ]
            for prioridad_id, categoria_id in actualizaciones:
                cur.execute("UPDATE categorias SET prioridad_id = %s WHERE id = %s", (prioridad_id, categoria_id))

            print("3. Haciendo la columna obligatoria y creando la relación FK...")
            cur.execute("ALTER TABLE categorias MODIFY COLUMN prioridad_id TINYINT UNSIGNED NOT NULL")
            cur.execute("""
                ALTER TABLE categorias 
                ADD CONSTRAINT fk_categorias_prioridad 
                FOREIGN KEY (prioridad_id) REFERENCES prioridades (id)
            """)
            
        con.commit()
        print("Migración completada con éxito.")
    except Exception as e:
        con.rollback()
        print(f"Error durante la migración: {e}")
    finally:
        con.close()

if __name__ == "__main__":
    migrar_categorias()