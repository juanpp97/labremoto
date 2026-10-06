# Backend — Laboratorio Remoto de Cinemática

Servidor Flask que controla el prototipo físico del laboratorio (MQTT) y garantiza que un solo usuario lo opere a la vez mediante un **lease con heartbeat**.

La documentación técnica completa está en [`technical.md`](technical.md).

## Inicio rápido

```bash
# Desarrollo: pruebas (no requieren hardware, MySQL ni red)
pip install -r requirements-dev.txt
python -m pytest -q

# Producción (Raspberry Pi)
cp .env.example .env            # completar JWT_KEY y DATABASE_URI
gunicorn -c gunicorn.conf.py app:app
```

Para el despliegue con systemd ver [`deploy/README.md`](deploy/README.md) y la sección [Configuración y despliegue](technical.md#9-configuración-y-despliegue).

## Estructura

```
Server/
├── app.py                 # punto de entrada: configuración, DB, login, cableado
├── LabRem.py              # cliente MQTT, procesamiento y gráficos (heredado)
├── gunicorn.conf.py       # 1 worker, 6 hilos
├── lease/                 # lease: lógica, API HTTP, historial, configuración
├── hardware/              # acceso físico: controlador con fencing, driver, rutas
├── migrations/            # SQL de la base de datos
├── deploy/                # unit de systemd y guía de despliegue
├── technical.md           # documentación técnica
├── docs/diagrams/         # diagramas: código Mermaid (.mmd) y SVG generados
└── tests/                 # 189 pruebas (unitarias y de API)
```
