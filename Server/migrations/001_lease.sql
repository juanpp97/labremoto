-- Migración 001: rol de usuario + historial de leases.
-- Ejecutar en el MySQL de producción ANTES de desplegar el servidor nuevo.
-- Verificar antes el nombre real de la tabla de usuarios (SHOW TABLES);
-- `user` es el nombre por defecto de Flask-SQLAlchemy para el modelo User.

-- 1) Rol de usuario ('user' | 'admin')
ALTER TABLE `user` ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';

-- Completar con los usernames (DNI) de los administradores/docentes:
-- UPDATE `user` SET role = 'admin' WHERE username IN ('...');

-- 2) Historial de leases (una fila por lease). Fechas en UTC.
CREATE TABLE lease_history (
    lease_id      CHAR(36)    NOT NULL,
    username      VARCHAR(80) NOT NULL,
    acquired_at   DATETIME    NOT NULL,
    ended_at      DATETIME    NULL,
    end_reason    VARCHAR(20) NULL,  -- expired | heartbeat_timeout | released | forced | server_shutdown | server_restart
    safe_state_ok TINYINT(1)  NULL,
    safe_state_ms INT         NULL,
    PRIMARY KEY (lease_id),
    INDEX idx_lease_history_acquired_at (acquired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
