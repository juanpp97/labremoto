"""Configuración de gunicorn para la Raspberry Pi.

    gunicorn -c gunicorn.conf.py app:app

El estado del lease vive en memoria: tiene que haber UN solo worker. Por eso `workers`
está fijo (no se lee del entorno) y, además, el servidor toma un lock de proceso al
arrancar (lease/process_lock.py), que cubre el caso de `--workers 2` por línea de comandos.
"""
import os

# El ProxyPass de Apache apunta a la IP de la Raspberry en el puerto 80.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:80")

workers = 1
worker_class = "gthread"
# Cámara + comando + heartbeat del usuario activo ocupan 3 hilos; el resto queda de margen
# (polling de /status, login, y el admin necesita un hilo libre para force-release).
threads = int(os.environ.get("GUNICORN_THREADS", "6"))

# Tiempo que tiene el worker para terminar el reset de apagado (safe_state) tras un SIGTERM.
graceful_timeout = 120
keepalive = 5

# Logs a stdout (journald). El access log está apagado por defecto: el heartbeat cada 20 s
# genera muchas líneas y desgasta la SD. Con GUNICORN_ACCESSLOG=1 se registra la IP real
# del cliente (X-Forwarded-For que agrega Apache).
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
accesslog = "-" if os.environ.get("GUNICORN_ACCESSLOG") == "1" else None
access_log_format = '%({x-forwarded-for}i)s "%(r)s" %(s)s %(L)s'
