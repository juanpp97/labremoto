# Despliegue en la Raspberry Pi

Arquitectura: navegador → Apache de la facultad (HTTPS, sesiones PHP) → proxy inverso
`/raspi` → `http://<IP de la Raspberry>:80` → gunicorn (1 worker, 6 hilos) → Flask.

## Instalación

```bash
sudo useradd --system --home /opt/labrem labrem            # o el usuario que prefieras
cd /opt/labrem && python3 -m venv venv
venv/bin/pip install -r Server/requirements.txt
cp Server/.env.example Server/.env                          # completar JWT_KEY y DATABASE_URI
sudo cp Server/deploy/labrem.service /etc/systemd/system/   # ajustar User/Group/rutas
sudo systemctl daemon-reload && sudo systemctl enable --now labrem
```

Antes del primer arranque, ejecutar en MySQL `Server/migrations/001_lease.sql` y
configurar el cron del servidor PHP con `Server/migrations/purge_lease_history.sql`.

## Qué esperar al arrancar

1. El proceso toma un lock de archivo (`LEASE_LOCK_FILE`). Un segundo proceso o worker
   **falla al arrancar** con `ProcessLockError`: el estado del lease vive en memoria.
2. El recurso nace en `RESETTING` y corre `safe_state` en segundo plano. Hasta que termine,
   `/resource/status` informa `RESETTING` y `acquire` responde 423 corto.
3. Si `safe_state` falla queda en `FAULT` (503 en `acquire`, y `/healthz` responde 503),
   con reintentos automáticos. `POST /admin/resource/force-release` fuerza un reintento.

## Monitoreo

`GET /healthz` (sin autenticación): 200 si el servicio está sano (también durante un
`RESETTING`), **503 si el hardware está en `FAULT`**. Incluye los contadores del historial
(`pending`, `dropped`).

## Logs

JSON, una línea por evento, a stdout (journald): `journalctl -u labrem -o cat`.
Cada transición del lease trae `event=lease_transition`, `from_state`, `to_state`,
`reason`, `user_id` y `epoch`. Nota: `user_id` es el DNI, es dato personal.

Para no desgastar la SD, dejar journald en memoria (`Storage=volatile` en
`/etc/systemd/journald.conf`). El access log de gunicorn viene apagado
(`GUNICORN_ACCESSLOG=1` para activarlo).

## Apache

- El proxy reenvía por defecto los headers personalizados, incluido `X-Lease-Token`:
  no hay que filtrarlos.
- El `release` responde al instante (el reset del hardware corre en segundo plano), así
  que el `ProxyTimeout` no es crítico.

## Operación

```bash
sudo systemctl restart labrem     # el safe_state de arranque deja el hardware en estado conocido
sudo systemctl stop labrem        # con sesión activa: la revoca y ejecuta safe_state (hasta ~2 min)
journalctl -u labrem -f -o cat
curl -i http://localhost/healthz
```
