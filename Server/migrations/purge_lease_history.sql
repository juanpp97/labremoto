-- Limpieza del historial de leases: borra las filas con más de 7 días.
-- Pensado para correr desde un cron del servidor PHP (por ejemplo, una vez por día).
-- Para cambiar la retención alcanza con modificar el intervalo; el servidor no purga.
--
-- Ejemplo de script PHP para el cron (credenciales propias del servidor):
--
--   <?php
--   $db = new mysqli($host, $user, $pass, 'LRFICA');
--   $db->query("DELETE FROM lease_history WHERE acquired_at < UTC_TIMESTAMP() - INTERVAL 7 DAY");
--   $db->close();

DELETE FROM lease_history WHERE acquired_at < UTC_TIMESTAMP() - INTERVAL 7 DAY;
