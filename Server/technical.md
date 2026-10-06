# Documentación técnica del backend

**Laboratorio Remoto de Cinemática — servidor de control del prototipo**

Este documento describe por completo el backend: qué problema resuelve, cómo está construido, cómo se comporta en cada situación, por qué se tomaron sus decisiones y cómo se opera. Está pensado para que un desarrollador entienda el sistema en detalle sin necesidad de leer el código.

---

## Índice

1. [Resumen](#1-resumen)
2. [Contexto del sistema](#2-contexto-del-sistema)
3. [Arquitectura](#3-arquitectura)
4. [Modelo de lease](#4-modelo-de-lease)
5. [Concurrencia y fencing](#5-concurrencia-y-fencing)
6. [Hardware](#6-hardware)
7. [Referencia de la API](#7-referencia-de-la-api)
8. [Historial de leases](#8-historial-de-leases)
9. [Configuración y despliegue](#9-configuración-y-despliegue)
10. [Pruebas](#10-pruebas)
11. [Decisiones de arquitectura](#11-decisiones-de-arquitectura)
12. [Limitaciones y deuda técnica](#12-limitaciones-y-deuda-técnica)
13. [Glosario](#13-glosario)

> **Sobre los diagramas.** Son imágenes SVG con fondo blanco generadas a partir de su código Mermaid, que está en [`docs/diagrams/`](docs/diagrams/) (un archivo `.mmd` por diagrama y una configuración visual común en `mermaid-config.json`). Para modificar uno se edita su `.mmd` y se ejecuta `docs/diagrams/render.sh`. Se publican como imágenes y no como bloques Mermaid porque los visores de Markdown dibujan esos bloques sobre el fondo de su tema (oscuro en VS Code o GitHub con tema oscuro), lo que vuelve ilegibles las líneas y los textos.

---

## 1. Resumen

El laboratorio tiene **un único prototipo físico**: una rampa de inclinación variable, un móvil con acelerómetro y sensores de barrera, controlados por dos microcontroladores que se comunican por **MQTT** con una **Raspberry Pi**. En la Raspberry corre una aplicación **Flask** servida por **gunicorn**, que expone una API HTTP. El frontend la consume a través del **proxy inverso Apache** de la facultad.

Como el hardware es uno solo, el problema central es la **exclusión mutua**. Un único usuario debe operar el prototipo a la vez, durante un tiempo acotado, y el recurso debe liberarse de forma confiable aunque el usuario desaparezca (cierre la pestaña o pierda la red). El backend lo resuelve con un **lease de recurso con heartbeat**:

| Mecanismo | Función |
|---|---|
| **JWT** | Identifica al usuario (quién es). |
| **Lease** | Autoriza a operar el hardware ahora. Dura como máximo 15 minutos, se mantiene vivo con heartbeats y se libera solo si dejan de llegar. |
| **`safe_state`** | Cada vez que una sesión termina, por la causa que sea, el prototipo vuelve a un estado seguro (rampa a 0°) antes de entregarse a otro usuario. |
| **Fencing por época** | Garantiza que ningún comando se ejecute sobre el hardware después de que terminó la sesión que lo envió. |
| **Historial** | Registra cada sesión en MySQL para auditoría, sin que una falla de la base afecte al laboratorio. |

---

## 2. Contexto del sistema

![Contexto del sistema](docs/diagrams/01-contexto.svg)


| Actor | Rol | Relación con el backend |
|---|---|---|
| Navegador | Interfaz del alumno: predicciones, control del experimento, video y resultados. | HTTP vía Apache (`/raspi/...`). |
| Apache | Termina HTTPS y reenvía `/raspi` a la Raspberry. Reenvía los headers personalizados, incluido `X-Lease-Token`. | Proxy inverso. |
| Sitio PHP | Autenticación institucional. El frontend lo consulta para obtener el usuario (DNI) antes de pedir el JWT. Un cron del mismo servidor purga el historial. | Ninguna directa. |
| MySQL | Usuarios (con rol) e historial de sesiones. | SQLAlchemy (`mysql+pymysql`). |
| Broker MQTT | Intermedia los mensajes entre la Raspberry y los microcontroladores. | `paho-mqtt`. |
| Microcontroladores | Ejecutan los comandos físicos y publican estado y mediciones. | Vía broker. |
| Webcam | Video en vivo del prototipo. | Lectura local (`imageio`). |

### Responsabilidades del backend

1. **Identidad:** emitir un JWT a usuarios registrados.
2. **Acceso exclusivo:** administrar el lease (adquirir, mantener, liberar, vencer).
3. **Seguridad física:** devolver el prototipo a un estado seguro al terminar cada sesión e impedir que un comando de una sesión terminada llegue al hardware.
4. **Experimento:** inclinar la rampa, ejecutar el experimento, reiniciar y generar los gráficos.
5. **Video:** transmitir la cámara solo al titular del lease.
6. **Auditoría:** registrar cada sesión.
7. **Operabilidad:** salud del servicio, logs estructurados, protección contra configuraciones peligrosas.

---

## 3. Arquitectura

### 3.1 Componentes

El código está organizado en capas. La lógica que decide **quién puede operar y cuándo** (`LeaseManager`) no conoce Flask ni MQTT. Eso permite probarla con un reloj y un hardware falsos.

![Componentes del backend](docs/diagrams/02-componentes.svg)


| Módulo | Responsabilidad |
|---|---|
| `app.py` | Punto de entrada. Lee la configuración, define los modelos (`User`, `TokenBlocklist`, `LeaseHistory`), el login y la verificación de rol, conecta MQTT y llama a `setup_resource`. |
| `lease/manager.py` | `LeaseManager`: estado del recurso, tokens, vencimientos, watchdog, reset, reintentos y eventos de auditoría. Lógica pura, sin Flask ni hardware. |
| `lease/flask_api.py` | Endpoints del lease, del administrador y de salud; decorador `@lease_required`; traducción de errores de dominio a HTTP. |
| `lease/wiring.py` | `setup_resource()`: crea y conecta controlador, manager e historial; registra los endpoints; arranca los hilos. |
| `lease/history.py` | `HistoryRecorder`: escritura asíncrona del historial con respaldo en memoria. |
| `lease/sql_history.py` | Modelo `lease_history` y store SQLAlchemy. |
| `lease/models.py`, `errors.py`, `clock.py` | Tipos de dominio, excepciones y reloj monotónico inyectable. |
| `lease/settings.py`, `process_lock.py`, `logging_config.py` | Configuración, lock de proceso único y logs JSON. |
| `hardware/controller.py` | `HardwareController`: único punto de acceso físico; `io_lock` y verificación de época. |
| `hardware/labrem_driver.py` | `LabRemDriver`: `safe_state` real sobre `LabRem`. |
| `hardware/routes.py` | Endpoints de hardware y cámara. Recibe el módulo `LabRem` por inyección. |
| `hardware/fake.py` | Doble de prueba del driver. |
| `LabRem.py` | Módulo heredado: cliente MQTT, comandos, recepción de mediciones, procesamiento numérico y gráficos (matplotlib). |

### 3.2 Dos credenciales: identidad y acceso

La versión anterior usaba el JWT también como lock del laboratorio, lo que impedía detectar desconexiones y producía liberaciones incorrectas. Ahora identidad y acceso están separados.

![Credenciales: identidad y acceso](docs/diagrams/03-credenciales.svg)


- Un JWT válido **no** alcanza para mover el hardware.
- El lease token **no** sirve como ticket de cámara, y viceversa. El ticket de cámara viaja en la URL (un `<img>` no puede enviar headers), por eso tiene privilegios mínimos.

### 3.3 Proceso e hilos

Hay **un único proceso** (gunicorn con un worker). El estado del lease vive en su memoria, por lo que un segundo proceso está prohibido (ver [5.6](#56-un-único-proceso)). Dentro del proceso conviven estos hilos:

| Hilo | Existe | Función |
|---|---|---|
| Pool de gunicorn (6) | Siempre | Atiende requests. Un stream de cámara ocupa un hilo mientras está abierto. |
| `lease-watchdog` | Siempre | Cada 5 s revisa si el lease venció o perdió el heartbeat. Captura toda excepción: nunca muere. |
| `lease-reset` | Al terminar cada lease | Ejecuta `safe_state` en segundo plano; los requests no lo esperan. |
| `lease-startup-reset` | Al arrancar | `safe_state` inicial para dejar el hardware en estado conocido. |
| `lease-safe-state-retry` | Solo en `FAULT` | Reintenta `safe_state` con backoff exponencial (2 s → 30 s). |
| `lease-history` | Si el historial está activo | Escribe el historial en MySQL y reintenta si la base falla. |
| `paho-mqtt` | Siempre | Loop de red MQTT; sus callbacks actualizan las variables globales de `LabRem`. |

### 3.4 Ciclo de vida de un comando

Ejemplo: el usuario inclina la rampa a 10°.

![Ciclo de vida de un comando](docs/diagrams/04-ciclo-de-un-comando.svg)


- La validación del paso 2 **cuenta como heartbeat**: quien envía comandos está presente.
- La re-verificación de la época **dentro** del `io_lock` (paso 5) impide que un comando encolado se ejecute después de que la sesión terminó.
- El `LeaseManager` nunca mantiene su lock durante la operación física.

### 3.5 Arranque

gunicorn importa `app.py` al iniciar el worker. El arranque **no espera** al hardware: el reset inicial corre en segundo plano.

![Arranque del servidor](docs/diagrams/05-arranque.svg)


Hasta que el reset inicial termina, `/resource/status` informa `RESETTING` y `acquire` responde `423`. Si falla, el recurso queda en `FAULT`, visible en `/resource/status` y `/healthz`, con reintentos automáticos.

### 3.6 Apagado

Ante un `SIGTERM` (por ejemplo `systemctl stop`), gunicorn deja de aceptar requests y los handlers `atexit` se ejecutan en este orden:

1. **`LeaseManager.stop()`**: detiene el watchdog y los hilos de fondo, esperando un reset en curso. Si hay una sesión activa, la termina con motivo `server_shutdown` y ejecuta `safe_state` **de forma sincrónica**. Sin sesión, igual ejecuta `safe_state`. Es idempotente.
2. **`HistoryRecorder.stop()`**: último intento de escribir lo pendiente.

gunicorn concede 120 s (`graceful_timeout`) y systemd 150 s (`TimeoutStopSec`). Un apagado abrupto (`kill -9`, corte de luz) no ejecuta nada de esto. Lo cubren el `safe_state` del siguiente arranque y el cierre de sesiones huérfanas del historial.

---

## 4. Modelo de lease

El `LeaseManager` (`lease/manager.py`) administra un único recurso, el prototipo, y decide en todo momento quién puede operarlo.

### 4.1 Requisitos

| Id | Requisito |
|---|---|
| RF1 | Un solo usuario con lease activo a la vez. |
| RF2 | Duración máxima de 15 min, **no renovable** por heartbeat. |
| RF3 | Liberación por release, vencimiento, pérdida de heartbeat, apagado del servidor o decisión de un administrador. |
| RF4 | Todo endpoint que actúa sobre el hardware exige lease válido. |
| RF5 | El cliente puede consultar disponibilidad y tiempo restante. |
| RF6 | Si el recurso está ocupado, el cliente recibe `423` con tiempo estimado. |
| RNF1 | Tras desaparecer el cliente, liberación en ≤ 80 s (`heartbeat_timeout + watchdog_tick`; objetivo ≤ 90 s). |
| RNF2 | Ningún comando se ejecuta después de que comenzó el `safe_state` de su sesión. |
| RNF3 | Un reinicio del servidor no deja el hardware en estado desconocido. |
| RNF4 | La lógica es testeable sin HTTP, sin hardware y sin esperar tiempo real. |
| RNF5 | Una falla de `safe_state` es un estado explícito y visible. |

### 4.2 Máquina de estados

![Máquina de estados del lease](docs/diagrams/06-estados-del-lease.svg)


| Estado | Significado | `acquire` responde | `/resource/status` |
|---|---|---|---|
| `FREE` | Libre y en estado seguro. | `200` con un lease nuevo. | `available: true`, `0` s |
| `LOCKED` | Hay un titular operando. Heartbeats y comandos lo mantienen vivo. | `423` a otro usuario; el mismo lease al titular. | `available: false`, segundos hasta el límite duro |
| `RESETTING` | La sesión terminó, los tokens ya están revocados y `safe_state` está en curso. | `423` con `10` s (estimación fija). | `available: false`, `10` |
| `FAULT` | `safe_state` falló; el hardware no quedó seguro. | `503`. | `available: false`, `null` |

**Reglas:**

- Solo desde `FREE` se emite un lease nuevo.
- `LOCKED → RESETTING` **revoca los tokens en el mismo instante**, antes de tocar el hardware.
- `RESETTING → FREE` solo si `safe_state` terminó bien. Si falla, el recurso queda en `FAULT` y no se entrega: con hardware físico, liberar sin garantía de estado seguro es peor que negar el servicio.
- El servidor arranca en `RESETTING`, porque tras un reinicio el estado del hardware es desconocido.

### 4.3 Credenciales de un lease

| Identificador | Formato | Visible al cliente | Uso |
|---|---|:---:|---|
| `lease_token` | `secrets.token_urlsafe(32)` | Sí | Autoriza comandos, heartbeat y release. Se compara en tiempo constante. |
| `stream_token` | `secrets.token_urlsafe(32)` | Sí | Autoriza solo la cámara. No cuenta como heartbeat. |
| `epoch` | Entero creciente | No | *Fencing token*: identifica la sesión dentro del proceso. |
| `lease_id` | UUID v4 | No | Clave del historial (la época se reinicia con cada arranque). |

El manager recuerda **solo el último lease terminado** (su token y su motivo) para responder un `401` informativo cuando el cliente usa un token viejo.

### 4.4 Tiempos

| Parámetro | Default | Significado |
|---|---|---|
| `LEASE_DURATION_S` | 900 s | Límite duro. **Nunca se extiende.** |
| `HEARTBEAT_EVERY_S` | 20 s | Intervalo de heartbeat indicado al cliente. |
| `HEARTBEAT_TIMEOUT_S` | 75 s | Sin señales de vida durante este tiempo, el lease termina. |
| `WATCHDOG_TICK_S` | 5 s | Período del watchdog. |

Se valida al arrancar que `0 < heartbeat_every < heartbeat_timeout < lease_duration`.

**¿Por qué 20 s y 75 s?** Los navegadores reducen la frecuencia de los timers en pestañas en segundo plano (Chrome puede bajarlos a una ejecución por minuto). Con un timeout de 45 s, un usuario con la pestaña de fondo perdería la sesión. 75 s tolera ese throttling, y 75 + 5 = 80 s cumple el objetivo de liberación.

![Detección de heartbeat perdido](docs/diagrams/07-heartbeat.svg)


Con heartbeats constantes, la sesión igual termina a los 900 s, con motivo `expired`.

Todos los plazos usan un **reloj monotónico**. La Raspberry no tiene reloj con batería, y su hora de pared puede saltar al sincronizar NTP después del arranque. El reloj de pared se usa solo para los timestamps del historial.

### 4.5 Señales de vida

| Cuenta como heartbeat | No cuenta |
|---|---|
| `POST /resource/heartbeat` | El stream de `/camera` (puede quedar abierto en una pestaña abandonada) |
| Cualquier request protegido con `@lease_required` (comandos y gráficos) | `GET /resource/status` |
| Un re-acquire del titular | |

### 4.6 Detección de vencimiento

El vencimiento se detecta por dos caminos complementarios:

1. **Watchdog:** cada 5 s llama a `tick()`. Garantiza la liberación aunque no llegue ningún request.
2. **Chequeo perezoso:** cada operación del manager evalúa primero el vencimiento, así un request que llega justo después ve el estado correcto sin esperar al próximo tick.

Primero se evalúa el límite duro (`expired`) y después el heartbeat (`heartbeat_timeout`). Este es el flujo de `validate(token)`:

![Flujo de validate(token)](docs/diagrams/08-validacion-del-token.svg)


`is_current(epoch)` y `validate_stream` son **chequeos puros**: consideran el vencimiento pero no provocan transiciones. `is_current` se llama con el `io_lock` del hardware tomado y no debe disparar un `safe_state`, que necesita ese mismo lock.

### 4.7 Causas de fin de sesión

| `reason` | Causa | Quién la detecta |
|---|---|---|
| `released` | El usuario terminó la sesión. | `POST /resource/release` |
| `expired` | Se alcanzaron los 15 min. | Watchdog o chequeo perezoso |
| `heartbeat_timeout` | 75 s sin señales de vida. | Watchdog o chequeo perezoso |
| `forced` | Un administrador liberó el recurso. | `POST /admin/resource/force-release` |
| `server_shutdown` | El servidor se apagó con una sesión activa. | `LeaseManager.stop()` |
| `server_restart` | El proceso murió abruptamente con una sesión abierta. | Solo en el historial, al arrancar |
| `unknown` | El token no corresponde al último lease terminado. | Validación |

### 4.8 Liberación asíncrona

Toda terminación originada en un request (release, force-release, vencimiento detectado por un request) **no espera al hardware**. `safe_state` puede tardar más de un minuto y medio en el peor caso. Esperarlo bloquearía un hilo de gunicorn y chocaría con el timeout del proxy.

![Liberación asíncrona](docs/diagrams/09-release-asincrono.svg)


El **apagado del servidor** es la única excepción: ahí `safe_state` es sincrónico, porque después no queda nadie que lo termine. Un efecto visible: un `acquire` que llega justo después de un vencimiento recibe `423` corto en lugar de esperar el reset.

### 4.9 Re-acquire idempotente

Si el **mismo usuario** pide el lease mientras el suyo está vigente, recibe **el mismo lease** (mismos tokens, misma época, tiempo restante actual) y la llamada cuenta como heartbeat. Así se recupera la sesión tras recargar la página aunque se haya perdido el token. Como consecuencia, dos pestañas del mismo usuario comparten la sesión. Otro usuario recibe `423`.

### 4.10 Falla del hardware y reintentos

![Falla del hardware y reintentos](docs/diagrams/10-fault-y-reintentos.svg)


- Cada falla registra un error en el log con su traceback.
- Mientras dura un intento, el estado es `RESETTING`.
- El hilo de reintento termina solo cuando el recurso sale de `FAULT`, ya sea por un intento propio o por la acción de un administrador.
- Cada intento queda registrado en el historial del lease afectado.

### 4.11 Interfaz del `LeaseManager`

| Método | Devuelve | Lanza | Notas |
|---|---|---|---|
| `acquire(user_id)` | `LeaseGrant` | `ResourceBusy`, `ResourceFault` | Idempotente para el titular. |
| `renew(token)` | segundos restantes | `LeaseInvalid` | Heartbeat. Nunca extiende el límite. |
| `validate(token)` | `LeaseContext` | `LeaseInvalid` | Cuenta como heartbeat. |
| `validate_stream(token)` | época | `LeaseInvalid` | Chequeo puro, no es heartbeat. |
| `is_current(epoch)` | `bool` | — | Chequeo puro para el fencing. |
| `release(token)` | — | `LeaseInvalid` | No espera al hardware. |
| `force_release(reason)` | `bool` | — | En `LOCKED` termina la sesión; en `FAULT` fuerza un reintento. |
| `status()` | `StatusSnapshot` | — | Nunca expone al usuario. |
| `reason_for(token)` | `EndReason` | — | Motivo de fin del último lease, si el token es el suyo. |
| `start(initial_reset)` / `stop()` | — | — | Ver [3.5](#35-arranque) y [3.6](#36-apagado). |

El constructor recibe el hardware (cualquier objeto con `safe_state()`), el reloj, los tiempos, el backoff, el reloj de pared (para auditoría), un observador de eventos (`on_event`) y un ejecutor de resets (`reset_runner`).

---

## 5. Concurrencia y fencing

### 5.1 Locks

| Lock | Protege | Se mantiene durante |
|---|---|---|
| `LeaseManager._lock` | Estado del lease: estado, tokens, usuario, época, plazos, último motivo. | Microsegundos; **nunca** durante una operación física. |
| `HardwareController._io_lock` | El acceso físico: comandos, gráficos y `safe_state`. | Lo que dura la operación (hasta ~15 s un comando). |
| `HistoryRecorder._lock` | Registros de auditoría pendientes. | Microsegundos; **nunca** durante la escritura a la base. |

### 5.2 Orden de adquisición

![Orden de adquisición de locks](docs/diagrams/11-orden-de-locks.svg)


La única anidación posible sigue esa dirección. Con el `io_lock` tomado, el controlador consulta `is_current`, que toma brevemente el lock del manager. Con el lock del manager tomado, el observador de auditoría toma el lock del historial. **Ningún camino adquiere en sentido inverso**, por lo que no hay deadlock posible.

El observador se invoca con el lock del manager tomado para que los eventos lleguen en el mismo orden que las transiciones. Por eso su contrato es estricto: **no bloquea y no lanza**. Si lanzara, el manager registra la excepción y la ignora.

### 5.3 El manager nunca espera al hardware

Si `safe_state` se ejecutara con el lock del manager tomado, no se podría atender ningún heartbeat ni consulta mientras dura. Por eso toda terminación tiene dos fases:

1. **Bajo el lock:** transición a `RESETTING` y revocación de tokens (instantáneo).
2. **Sin el lock, en un hilo aparte:** `safe_state()`, y al terminar, de nuevo bajo el lock, la transición a `FREE` o `FAULT`.

### 5.4 La carrera crítica: comando contra expiración

Validar el token al inicio del request no alcanza. Entre la validación y la ejecución pasa tiempo, y la sesión puede terminar en ese intervalo:

![La carrera comando contra expiración](docs/diagrams/12-carrera-sin-fencing.svg)


**Solución: fencing por época** (cf. Kleppmann, *Designing Data-Intensive Applications*, cap. 8):

1. Cada `acquire` incrementa la época.
2. La validación devuelve el contexto con la época.
3. El `HardwareController` serializa **todo** acceso físico con su `io_lock`, **incluido `safe_state`**.
4. Ya dentro del `io_lock`, cada operación vuelve a preguntar `is_current(época)`. Si la sesión terminó, lanza `LeaseRevoked` (→ `401`) sin tocar el hardware.
5. `safe_state` toma el mismo `io_lock`: espera al comando que ya se estaba ejecutando, y todo lo que llega después falla en el paso 4.

![Fencing por época](docs/diagrams/13-fencing-por-epoca.svg)


Detalles de `HardwareController.run`:

- **Chequeo previo sin lock** (*fast-fail*): una sesión terminada falla de inmediato, sin encolarse detrás de un `safe_state` largo.
- **Chequeo dentro del lock:** es el que garantiza la seguridad. Atrapa al request que pasó el chequeo previo y quedó esperando mientras la sesión terminaba.
- **Sin verificador conectado, se niega a operar.**
- `is_current` considera vencido un lease cuyo plazo pasó, aunque el watchdog todavía no lo haya procesado.
- `safe_state` espera el `io_lock` como máximo **60 s**. Si no lo obtiene, falla y el recurso pasa a `FAULT`.

El comando en vuelo se **espera, no se aborta**: los comandos MQTT no pueden interrumpirse a mitad. Por eso la espera del experimento (5 s tras soltar el móvil) va dentro de la operación protegida, y el reset no puede mover la rampa mientras el móvil está bajando.

### 5.5 Invariantes

| # | Invariante | Mecanismo |
|---|---|---|
| I1 | Como máximo un lease vigente. | Emisión bajo lock y solo desde `FREE`. |
| I2 | El token se revoca antes de que el hardware empiece a resetearse. | Misma sección crítica que la transición a `RESETTING`. |
| I3 | Ningún comando se ejecuta después del inicio del `safe_state` de su sesión. | Fencing por época dentro del `io_lock`. |
| I4 | Solo se vuelve a `FREE` tras un `safe_state` exitoso. | `FREE` se asigna únicamente en ese punto. |
| I5 | Un `safe_state` por fin de sesión (más los reintentos en `FAULT`). | La transición a `RESETTING` ocurre una sola vez, y quien la hace agenda el reset. |
| I6 | El límite duro nunca se extiende. | Nada modifica el vencimiento después del `acquire`. |
| I7 | Ningún request espera al hardware para enterarse de que su sesión terminó. | Reset asíncrono y *fast-fail*. |
| I8 | El watchdog no muere. | Captura toda excepción. |
| I9 | Una falla del historial no afecta al lease ni al hardware. | El observador no bloquea ni lanza; la escritura ocurre en otro hilo. |

Todos están verificados por la suite de pruebas (ver [10](#10-pruebas)).

### 5.6 Un único proceso

Todo lo anterior supone que el estado vive en la memoria de **un** proceso. Con dos procesos, cada uno tendría su propio lease y dos usuarios podrían operar a la vez. Por eso:

- `gunicorn.conf.py` fija `workers = 1`, y ese valor no se lee del entorno.
- Al arrancar, el proceso toma un **lock exclusivo de archivo** (`fcntl.flock` en Linux, `msvcrt.locking` en Windows). Un segundo proceso falla de inmediato con `ProcessLockError`, antes de crear hilos o tocar el hardware. Esto cubre también `gunicorn --workers 2` por línea de comandos. El sistema operativo libera el lock si el proceso muere.

### 5.7 Estado de `LabRem` y el hilo MQTT

`LabRem.py` guarda el estado de la base y las mediciones en variables globales que actualiza el hilo de `paho-mqtt`. Los comandos y los gráficos se ejecutan bajo el `io_lock`, pero los callbacks MQTT no toman ese lock. Funciona en la práctica (las asignaciones son atómicas bajo el GIL y el prototipo publica un mensaje por vez), pero no está garantizado formalmente. Es deuda heredada.

---

## 6. Hardware

### 6.1 Comunicación MQTT

![Comunicación MQTT](docs/diagrams/14-mqtt.svg)


| Tópico | Dirección | Contenido |
|---|---|---|
| `/labRem/cinematica/baseCom` | Raspberry → ambos micros | Comandos `com0` a `com7`. |
| `/labRem/cinematica/baseInfo` | Base → Raspberry | Estado textual de la base (QoS 0). |
| `/labRem/cinematica/baseTiempo` | Base → Raspberry | Cuatro tiempos de los sensores de barrera al terminar el experimento (QoS 0). |
| `/labRem/cinematica/movilDatos` | Móvil → Raspberry | Muestras `t, ax, az` del acelerómetro, 200 por experimento (QoS 2). |

La conexión se establece al arrancar (`connect` + `loop_start`, keepalive 60 s).

| Comando | Acción | Uso |
|---|---|---|
| `com0` | No operación. | — |
| `com1` | Inicia el experimento: suelta el móvil y envía la telemetría. | `/iniciar` |
| `com2` | Envía telemetría. | — |
| `com3 ang X` | Inclina la rampa a X grados (0 a 15). | `/inclinar` |
| `com4` | Reinicia: rampa a 0°. | `/reiniciar`, `safe_state` |
| `com5` | Consulta el estado (responde por `baseInfo`). | Antes y durante cada comando |
| `com6` | Reset completo de los microcontroladores. | Respaldo de `safe_state` |
| `com7` | *Deep sleep* del móvil (no hay forma remota de despertarlo). | No se usa |

### 6.2 Estados de la base

![Estados de la base](docs/diagrams/15-estados-de-la-base.svg)


Borde verde: la base acepta comandos. Borde ámbar: estado transitorio, la base rechaza comandos. `Exp Reiniciado` es además el **estado seguro**. El firmware publica `ESPERANDO COMANDO` con tres espacios al final, y el código lo compara así.

### 6.3 Primitivas de `LabRem.py`

| Función | Comportamiento |
|---|---|
| `consultarEstado(target=0)` | Publica `com5`, espera 0,2 s y compara el estado. Con `target=0` acepta cualquier estado "lista"; con un `target` concreto, solo ese. |
| `enviarComandoBM(topic, msg, timeout, target=0)` | Si la base no está lista devuelve `0` sin enviar. Si lo está, publica y consulta repetidamente hasta alcanzar `target` (devuelve `1`) o agotar `timeout` (**lanza** `TimeOutError`). |
| `enviarAnguloCin(angulo)` | Valida 0 ≤ ángulo ≤ 15 (`AnguloInvalidoError`; un valor no numérico lanza `ValueError`) y envía `com3`, esperando `Base lista` 10 s. |
| `iniExp()` / `reinExp()` | `com1` / `com4`, timeout 10 s. |
| `hardReset()` | Publica `com6` sin esperar respuesta. |
| `GraficarDatos*()` | Generadores que producen un PNG con las mediciones globales. |

Con `target=0`, `enviarComandoBM` acepta cualquier estado "lista", incluido el que la base tenía **antes** de procesar el comando. Por eso `safe_state` pide explícitamente `Exp Reiniciado`. En `/iniciar` esto hace que `iniExp()` retorne casi de inmediato; la espera de 5 s posterior es la que realmente cubre el experimento.

### 6.4 `HardwareController`

`hardware/controller.py` es la **única** vía por la que el backend toca el prototipo. Envuelve a un driver intercambiable: `LabRemDriver` en producción y `FakeDriver` en pruebas.

| Método | Comportamiento |
|---|---|
| `attach_lease_checker(is_current)` | Conecta la verificación de época. Sin ella, `run` se niega a operar. |
| `run(contexto, operación)` | Chequeo de época sin lock → toma `io_lock` → chequeo de época → ejecuta. Si la sesión terminó: `LeaseRevoked`. |
| `safe_state()` | Toma `io_lock` (espera máxima 60 s, si no `HardwareError`) y delega en el driver. |

### 6.5 `safe_state`

`LabRemDriver.safe_state()` define el estado seguro como **la rampa en 0° con la base en `Exp Reiniciado`**. Es idempotente: se ejecuta al arrancar, al terminar cada sesión, al apagar y en cada reintento.

![Secuencia de safe_state](docs/diagrams/16-safe-state.svg)


- Cada intento espera hasta 30 s a que la base esté lista y luego envía `com4`, esperando hasta 10 s el estado `Exp Reiniciado`. Tras `com6` se esperan hasta 20 s a que los micros vuelvan a `ESPERANDO COMANDO`.
- La espera previa existe porque el reset puede llegar con la base a mitad de una maniobra, y en ese estado rechaza comandos.
- Si la base ya está en `Exp Reiniciado`, el intento no envía nada.
- **Tiempos:** en el caso normal tarda unos segundos. En el peor caso (espera del `io_lock`, ambos intentos y el reset de micros) supera el minuto y medio. Por eso nunca se ejecuta dentro de un request.

> **Pendiente de validar en el prototipo:** que `com4` funcione desde `ESPERANDO COMANDO` y que tras `com6` la rampa quede en 0°. Si no, la secuencia de respaldo terminaría en `FAULT` aunque el hardware esté bien.

### 6.6 El experimento

![El experimento de punta a punta](docs/diagrams/17-experimento.svg)


**Procesamiento de las mediciones:**

- **Barreras:** los cuatro tiempos parciales se acumulan para obtener el paso por cada sensor (posiciones fijas: 0; 0,02; 0,30; 0,60 y 0,90 m).
- **Acelerómetro:** muestreo a 100 Hz que empieza unos 2 s después del comando. La aceleración en x se convierte a m/s² y se integra con la regla del trapecio. Se grafica solo el intervalo que cubren las barreras, para excluir el golpe al frenar.
- **Respaldo:** sin datos del acelerómetro, la posición se interpola desde las barreras (polinomio de Lagrange) y se deriva numéricamente.

| Gráfico | Endpoint | Contenido |
|---|---|---|
| Sensores | `/grafica-sensores` | Posición de los sensores vs. tiempo, con interpolación. |
| Aceleración | `/resultados/grafica-aceleracion` | Acelerómetro, valor teórico g·sen(θ) y promedio. |
| Velocidad | `/resultados/grafica-velocidad` | Velocidad integrada. |
| Espacio | `/resultados/grafica-espacio` | Posición integrada. |

Los gráficos se generan a partir de las **últimas mediciones globales**: no se persisten ni se asocian a una sesión, y el siguiente experimento los sobrescribe. Solo el titular del lease puede pedirlos.

### 6.7 Rutas de hardware

Todas usan `@lease_required` y ejecutan su acceso físico mediante `HardwareController.run`.

| Ruta | Operación protegida | Particularidad |
|---|---|---|
| `POST /inclinar` | Consulta de estado + envío del ángulo, en una sola operación. | Ángulo inválido → `400 E02`. |
| `GET /iniciar` | `iniExp()` más la espera de 5 s. | El reset no puede mover la rampa durante el experimento. |
| `GET /reiniciar` | `reinExp()`. | — |
| Gráficos | Generación completa del PNG. | El generador se consume dentro de la operación; si no, correría fuera del `io_lock`. |

### 6.8 Cámara

La webcam es local, independiente del MQTT: no usa el `io_lock`, pero está ligada al lease.

![Stream de la cámara](docs/diagrams/18-camara.svg)


- Formato `multipart/x-mixed-replace; boundary=frame` con partes WEBP de 400×350 px.
- Headers `Cache-Control: no-store` y `X-Accel-Buffering: no`.
- El reader de la cámara se cierra siempre, ya sea porque terminó la sesión o porque el cliente cortó.
- Cada stream ocupa un hilo de gunicorn mientras está abierto.
- El paso del stream por el proxy de Apache ya se verificó con la versión anterior del servidor.

---

## 7. Referencia de la API

### 7.1 Generalidades

- **URL base en producción:** `https://labremotos.fica.unsl.edu.ar/raspi/`. Apache elimina el prefijo `/raspi` antes de reenviar.
- **Formato:** JSON, salvo los gráficos (`image/png`) y la cámara (`multipart/x-mixed-replace`).
- **CORS:** configurable con `CORS_ORIGINS` (default `*`). En producción frontend y API comparten dominio.

| Esquema | Cómo se envía | Lo emite | Vida |
|---|---|---|---|
| JWT (identidad) | `Authorization: Bearer <jwt>` | `POST /` | 1 h |
| Lease token (acceso) | `X-Lease-Token: <token>` (en `release` también en el body) | `POST /resource/acquire` | Hasta 15 min |
| Stream token (video) | `?t=<token>` | `POST /resource/acquire` | La del lease |

| Método | Ruta | Auth | Propósito |
|---|---|---|---|
| `POST` | `/` | — | Login: obtiene el JWT. |
| `POST` | `/resource/acquire` | JWT | Obtiene el lease. |
| `POST` | `/resource/heartbeat` | Lease | Señal de vida y tiempo restante. |
| `POST` | `/resource/release` | Lease | Termina la sesión. |
| `GET` | `/resource/status` | — | Estado y disponibilidad. |
| `POST` | `/inclinar` | Lease | Inclina la rampa. |
| `GET` | `/iniciar` | Lease | Ejecuta el experimento. |
| `GET` | `/reiniciar` | Lease | Rampa a 0°. |
| `GET` | `/grafica-sensores` y `/resultados/grafica-*` | Lease | Gráficos. |
| `GET` | `/camera?t=` | Stream token | Video en vivo. |
| `POST` | `/admin/resource/force-release` | JWT admin | Libera o fuerza un reintento en `FAULT`. |
| `GET` | `/admin/resource/history` | JWT admin | Historial de sesiones. |
| `GET` | `/healthz` | — | Salud del servicio. |

### 7.2 Flujo de un cliente

![Flujo de un cliente](docs/diagrams/19-flujo-del-cliente.svg)


**Recomendaciones para el cliente:**

1. Hacer heartbeat con el intervalo que indica el servidor (`heartbeat_every`), no con un valor fijo.
2. Basar la cuenta regresiva en `seconds_remaining`.
3. Al cerrar la pestaña (`pagehide`), liberar con `navigator.sendBeacon(url, JSON.stringify({lease_token}))`. `sendBeacon` no permite headers, por eso `release` acepta el token en el body, incluso como `text/plain`.
4. Guardar el `lease_token` en `sessionStorage`. Si se pierde, volver a pedir el lease: el titular recupera el mismo.
5. Mientras se espera, consultar `/resource/status` cada 30 a 60 s, o según `available_in_seconds`.
6. Descargar los gráficos antes de liberar.
7. Ante un `401`, mostrar un mensaje según `reason` (ver [7.9](#79-valores-de-reason)).

### 7.3 Login

**`POST /`** — Body JSON `{"username": "<DNI>"}`.

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200` | `{"token": "<jwt>"}` | El usuario existe. |
| `401` | `{"msg": "Credenciales Incorrectas", "code": "E00"}` | No existe. |

El backend no verifica contraseña: confía en que el frontend ya validó la sesión contra el sitio PHP (deuda conocida, ver [12.2](#122-seguridad)). El login no reserva el laboratorio.

**Errores del JWT** (en cualquier endpoint que lo requiera):

| Cuerpo | Causa |
|---|---|
| `{"msg": "No tienes permiso para acceder a esta url", "code": "F00"}` | Falta el header. |
| `{"msg": "Ya no puedes acceder a esta url", "code": "F01"}` | JWT vencido. |
| `{"msg": "Credenciales inválidas", "code": "F02"}` | JWT inválido. |
| `{"msg": "Token has been revoked"}` | `jti` en `TokenBlocklist`. |

Todos con código `401`.

### 7.4 Lease

**`POST /resource/acquire`** — Auth: JWT.

```json
{
  "lease_token": "q3V0…",
  "stream_token": "Zk9m…",
  "expires_in": 900,
  "heartbeat_every": 20,
  "heartbeat_timeout": 75
}
```

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200` | Lo de arriba. `expires_in` es menor a 900 en un re-acquire. | Lease emitido o re-acquire del titular. |
| `423` | `{"error": "resource_busy", "available_in_seconds": 642}` + header `Retry-After` | Otro titular (segundos hasta su límite) o `RESETTING` (10). |
| `503` | `{"error": "resource_fault"}` | Hardware en `FAULT`. |

**`POST /resource/heartbeat`** — Auth: `X-Lease-Token`.

| Código | Cuerpo |
|---|---|
| `200` | `{"seconds_remaining": 583}` (siempre decrece) |
| `401` | `{"error": "lease_invalid", "reason": "<motivo>"}` |

**`POST /resource/release`** — Responde de inmediato; el reset continúa en segundo plano. Toma el token del header `X-Lease-Token`, o del body JSON `{"lease_token": ...}` con cualquier `Content-Type`, o del campo de formulario `lease_token`.

| Código | Cuerpo |
|---|---|
| `200` | `{"status": "released"}` |
| `401` | `{"error": "lease_invalid", "reason": "<motivo>"}`. Si el lease ya había vencido, informa ese motivo y el reset se dispara igual. |

**`GET /resource/status`** — Sin autenticación; nunca revela quién usa el laboratorio.

```json
{"state": "LOCKED", "available": false, "available_in_seconds": 642}
```

| `state` | `available` | `available_in_seconds` |
|---|---|---|
| `FREE` | `true` | `0` |
| `LOCKED` | `false` | Hasta el límite duro (cota superior) |
| `RESETTING` | `false` | `10` (estimación) |
| `FAULT` | `false` | `null` |

### 7.5 Hardware

Todos requieren `X-Lease-Token`, **cuentan como heartbeat** y responden `401 {"error": "lease_invalid", "reason": ...}` si el lease no es válido o terminó mientras el comando esperaba. Un JWT no alcanza.

**`POST /inclinar`** — Formulario con `angulo` (0 a 15; si se omite, 0).

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200` | `{"msg": "Base Inclinada"}` | Posición confirmada. |
| `400` | `{"msg": "Ángulo Inválido", "code": "E02"}` | Fuera de rango o no numérico. |
| `400` | `{"msg": "Error al enviar comando", "code": "E01"}` | La base no estaba lista. |
| `400` | `{"msg": "Error al enviar comando"}` | La base rechazó el comando. |
| `504` | `{"msg": "Tiempo de espera agotado", "code": "E03"}` | Sin confirmación en 10 s. |

**`GET /iniciar`** — `200 {"msg": "Experimento realizado con éxito"}` · `400 E01` · `504 E03`.

**`GET /reiniciar`** — `200 {"msg": "Reiniciado correctamente"}` · `400 {"msg": "Ha ocurrido un error", "code": "E01"}` · `504 E03`.

**Gráficos** — `200 image/png`. `500` si todavía no hay mediciones válidas (antes del primer experimento).

**`GET /camera?t=<stream_token>`** — `200` stream. `401` si el ticket falta, es inválido, es el lease token o el lease terminó.

### 7.6 Administración

Requieren un JWT de un usuario con `role = 'admin'`. El rol se consulta en la base en cada llamada.

**`POST /admin/resource/force-release`**

| Situación | Efecto | Respuesta |
|---|---|---|
| Lease activo | Lo termina (`forced`) y agenda `safe_state`. | `200 {"status": "forced"}` |
| `FAULT` | Fuerza un reintento. | `200 {"status": "forced"}` |
| `FREE` o `RESETTING` | Nada. | `200 {"status": "noop"}` |
| Sin rol admin | — | `403 {"error": "forbidden"}` |

**`GET /admin/resource/history?limit=50`** — Del más reciente al más antiguo; `limit` entre 1 y 500.

```json
{
  "items": [{
    "lease_id": "8f0c2c3e-6a1b-4e0e-9a51-0c7f5d2a9e11",
    "username": "40722571",
    "acquired_at": "2026-10-05T14:02:11.120394+00:00",
    "ended_at": "2026-10-05T14:13:40.551203+00:00",
    "end_reason": "released",
    "safe_state_ok": true,
    "safe_state_ms": 3120,
    "persisted": true
  }],
  "pending_in_memory": 0,
  "dropped": 0
}
```

`persisted: false` indica que el registro todavía está solo en memoria. Errores: `403` sin rol, `404 {"error": "history_disabled"}` sin historial configurado, `503 {"error": "history_unavailable", "pending_in_memory": n}` si la base no responde.

### 7.7 Salud

**`GET /healthz`** — Sin autenticación.

```json
{"status": "ok", "lease_state": "LOCKED", "history": {"pending": 0, "dropped": 0}}
```

`200` si el servicio opera (`FREE`, `LOCKED` o `RESETTING`). `503` con `"status": "fault"` si el hardware está en `FAULT`.

### 7.8 Catálogo de errores

| HTTP | Identificador | Significado |
|---|---|---|
| `400` | `E01` | La base no está lista o rechazó el comando. |
| `400` | `E02` | Ángulo inválido. |
| `401` | `E00` | Usuario inexistente en el login. |
| `401` | `F00` · `F01` · `F02` | JWT ausente · vencido · inválido. |
| `401` | `lease_invalid` + `reason` | Lease ausente, inválido o terminado. |
| `403` | `forbidden` | Se requiere rol admin. |
| `404` | `history_disabled` | Historial no configurado. |
| `423` | `resource_busy` | Ocupado o reseteando. Incluye `Retry-After`. |
| `503` | `resource_fault` | Hardware en falla. |
| `503` | `history_unavailable` | No se pudo leer el historial. |
| `504` | `E03` | La base no respondió a tiempo. |

### 7.9 Valores de `reason`

| `reason` | Mensaje sugerido |
|---|---|
| `released` | Finalizaste la sesión. |
| `expired` | Se terminó el tiempo de la sesión. |
| `heartbeat_timeout` | La sesión se cerró por inactividad o pérdida de conexión. |
| `forced` | Un administrador finalizó la sesión. |
| `server_shutdown` | El laboratorio se reinició. Volvé a ingresar. |
| `unknown` | La sesión no es válida. Volvé a ingresar. |

### 7.10 Ejemplos

```bash
BASE=https://labremotos.fica.unsl.edu.ar/raspi
JWT=$(curl -s -X POST $BASE/ -H 'Content-Type: application/json' -d '{"username":"40722571"}' | jq -r .token)
TOKEN=$(curl -s -X POST $BASE/resource/acquire -H "Authorization: Bearer $JWT" | jq -r .lease_token)

curl -s -X POST $BASE/inclinar -H "X-Lease-Token: $TOKEN" -d angulo=10
curl -s $BASE/iniciar -H "X-Lease-Token: $TOKEN"
curl -s $BASE/resultados/grafica-aceleracion -H "X-Lease-Token: $TOKEN" -o aceleracion.png
curl -s -X POST $BASE/resource/heartbeat -H "X-Lease-Token: $TOKEN"
curl -s -X POST $BASE/resource/release -H 'Content-Type: text/plain' -d "{\"lease_token\":\"$TOKEN\"}"
curl -s $BASE/resource/status
curl -si $BASE/healthz
```

---

## 8. Historial de leases

El historial registra **cada sesión**: quién la tuvo, cuándo empezó y terminó, por qué terminó y si el hardware volvió al estado seguro.

### 8.1 Objetivos

| Objetivo | Cómo se cumple |
|---|---|
| Una falla de la base de datos nunca afecta al laboratorio. | Escritura asíncrona en un hilo propio. |
| No perder registros si la base cae un tiempo. | Respaldo en memoria con reintentos y backoff. |
| No desgastar la tarjeta SD. | El respaldo es **solo en memoria**, nunca en archivos. |
| Memoria acotada. | Máximo 1000 registros pendientes. |
| Reconstruir sesiones interrumpidas por un corte. | Al arrancar se cierran las que quedaron abiertas. |
| Retención acotada (contiene DNI). | Purga a los 7 días por un job externo. |

### 8.2 Modelo de datos

Una fila por lease. La relación con `user` es lógica, sin clave foránea, para que el historial sobreviva a la baja de un usuario.

![Modelo de datos del historial](docs/diagrams/20-modelo-de-datos.svg)


| Columna | Tipo MySQL | Descripción |
|---|---|---|
| `lease_id` | `CHAR(36)` PK | UUID del lease. |
| `username` | `VARCHAR(80)` | Titular (DNI). |
| `acquired_at` | `DATETIME`, indexado | Inicio en UTC. |
| `ended_at` | `DATETIME` nulo | Fin en UTC. |
| `end_reason` | `VARCHAR(20)` nulo | `released`, `expired`, `heartbeat_timeout`, `forced`, `server_shutdown`, `server_restart`. |
| `safe_state_ok` | `TINYINT(1)` nulo | Resultado del último `safe_state` de la sesión. |
| `safe_state_ms` | `INT` nulo | Duración de ese intento. |

### 8.3 De eventos a filas

![De eventos a filas](docs/diagrams/21-historial-eventos.svg)


| Evento | Completa |
|---|---|
| `started` (acquire) | `lease_id`, `username`, `acquired_at` |
| `ended` (fin de sesión) | `ended_at`, `end_reason` |
| `reset_done` (fin de `safe_state`) | `safe_state_ok`, `safe_state_ms`. Cada reintento en `FAULT` emite uno; queda el último. |

El re-acquire, los `acquire` rechazados y el reset de arranque no emiten eventos.

**Escritura idempotente:** el hilo escritor no envía eventos sueltos sino el **registro completo** con un upsert. El orden y la cantidad de intentos no importan: si el inicio no se pudo escribir porque la base estaba caída, el registro que se escribe después ya incluye inicio y fin.

**Reglas del escritor:**

- Cada registro lleva un número de secuencia. Solo se marca como escrito si no cambió durante la escritura.
- Un registro escrito y completo se libera de memoria. Uno cuyo `safe_state` falló se conserva, para que el reintento exitoso actualice la misma fila.
- Si la base falla, reintenta con backoff de 5 a 60 s.
- Con más de 1000 pendientes descarta el más viejo **ya terminado** (nunca una sesión abierta) y lo cuenta en `dropped`.
- Si el proceso muere con registros solo en memoria, se pierden. Es una decisión consciente para no escribir en la SD.

![Historial con la base de datos caída](docs/diagrams/22-historial-db-caida.svg)


Mientras la base está caída, `GET /admin/resource/history` muestra el registro con `persisted: false` y `/healthz` informa `pending: 1`.

### 8.4 Sesiones huérfanas

Si el proceso muere abruptamente con una sesión abierta, su fila queda con `ended_at` nulo. Al arrancar, antes de escribir nada más, el escritor ejecuta:

```sql
UPDATE lease_history
   SET ended_at = <ahora>, end_reason = 'server_restart'
 WHERE ended_at IS NULL AND acquired_at < <instante de arranque>;
```

La condición sobre el instante de arranque evita cerrar una sesión iniciada después del arranque. `ended_at` registra cuándo se detectó el corte, no el instante real de la caída (que es desconocido).

### 8.5 Purga y consulta

El servidor no borra filas. Un cron del servidor PHP ejecuta `migrations/purge_lease_history.sql`:

```sql
DELETE FROM lease_history WHERE acquired_at < UTC_TIMESTAMP() - INTERVAL 7 DAY;
```

Ejemplo de consulta directa, sesiones cuyo reset falló:

```sql
SELECT username, acquired_at, ended_at, end_reason, safe_state_ms
  FROM lease_history WHERE safe_state_ok = 0 ORDER BY acquired_at DESC;
```

---

## 9. Configuración y despliegue

### 9.1 Topología

![Topología de despliegue](docs/diagrams/23-topologia-de-despliegue.svg)


### 9.2 Variables de entorno

| Grupo | Lo lee | Fuentes, por prioridad |
|---|---|---|
| Aplicación | `app.py` y `lease/settings.py` (`python-decouple`) | Entorno del proceso → archivo `.env` del directorio de trabajo → default. |
| `GUNICORN_*` | `gunicorn.conf.py` (`os.environ`) | **Solo** el entorno del proceso. **No** se leen del `.env`: en producción van en la unit de systemd (`Environment=`). |

| Variable | Default | Descripción |
|---|---|---|
| `JWT_KEY` | **obligatoria** | Secreto de firma del JWT. |
| `DATABASE_URI` | **obligatoria** | URI de SQLAlchemy, p. ej. `mysql+pymysql://usuario:clave@10.150.0.101:3306/LRFICA`. |
| `JWT_LIFETIME_S` | `3600` | Vida del login (no de la sesión de laboratorio). |
| `LEASE_DURATION_S` | `900` | Límite duro de la sesión. |
| `HEARTBEAT_EVERY_S` | `20` | Intervalo de heartbeat. |
| `HEARTBEAT_TIMEOUT_S` | `75` | Tiempo sin señales que termina la sesión. |
| `WATCHDOG_TICK_S` | `5` | Período del watchdog. |
| `SAFE_STATE_RETRY_INITIAL_S` | `2` | Primer reintento en `FAULT`. |
| `SAFE_STATE_RETRY_MAX_S` | `30` | Reintento máximo en `FAULT`. |
| `LEASE_LOCK_FILE` | `<tmp>/labrem-lease.lock` | Lock de proceso único. Vacío lo desactiva (solo pruebas). |
| `LOG_LEVEL` | `INFO` | Nivel de log. |
| `LOG_FORMAT` | `json` | `json` o `text`. |
| `CORS_ORIGINS` | `*` | Orígenes permitidos, separados por comas. |
| `GUNICORN_BIND` | `0.0.0.0:80` | Dirección de escucha. |
| `GUNICORN_THREADS` | `6` | Hilos del worker. |
| `GUNICORN_LOGLEVEL` | `info` | Log de gunicorn. |
| `GUNICORN_ACCESSLOG` | apagado | `1` activa el access log con la IP real (`X-Forwarded-For`). |

`Server/.env.example` lista todas. **Valores fijos en el código:** `workers = 1`, `graceful_timeout = 120 s`, estimación de `RESETTING` 10 s, espera máxima del `io_lock` en `safe_state` 60 s, tiempos del driver 30/10/20 s, historial 1000 pendientes con backoff 5-60 s, broker `10.42.0.1:1883`.

### 9.3 gunicorn

```bash
gunicorn -c gunicorn.conf.py app:app
```

| Parámetro | Valor | Motivo |
|---|---|---|
| `workers` | `1` | Estado en memoria. Reforzado por el lock de proceso. |
| `worker_class` | `gthread` | Concurrencia con hilos dentro del único proceso. |
| `threads` | `6` | El usuario activo ocupa hasta 3 hilos (cámara, comando, heartbeat). El resto cubre el polling de otros usuarios, una recarga con el stream anterior todavía abierto, y garantiza un hilo libre para `force-release`. |
| `bind` | `0.0.0.0:80` | El `ProxyPass` de Apache apunta al puerto 80. |
| `graceful_timeout` | `120` | Tiempo para el `safe_state` de apagado. |
| `accesslog` | apagado | Con un heartbeat cada 20 s generaría miles de líneas por día y desgastaría la SD. |

`python app.py` levanta el servidor de desarrollo de Flask. No debe usarse en producción.

### 9.4 systemd

Archivo `deploy/labrem.service`. `User`, `Group` y las rutas son plantillas a ajustar.

| Directiva | Valor | Motivo |
|---|---|---|
| `ExecStart` | `…/venv/bin/gunicorn -c gunicorn.conf.py app:app` | — |
| `WorkingDirectory` | carpeta `Server/` | `python-decouple` busca el `.env` ahí. |
| `Restart` | `always`, `RestartSec=3` | Tras una caída, el `safe_state` de arranque deja el hardware en estado conocido. |
| `AmbientCapabilities` | `CAP_NET_BIND_SERVICE` | Puerto 80 sin ejecutar como root. |
| `NoNewPrivileges` | `true` | Endurecimiento. |
| `TimeoutStopSec` | `150` | Mayor que `graceful_timeout`. |

![Arranque y apagado con systemd](docs/diagrams/24-systemd.svg)


### 9.5 Apache

- El `ProxyPass` existente (`/raspi` → `http://10.150.0.102:80`) es suficiente.
- Apache reenvía los headers personalizados por defecto; `X-Lease-Token` no requiere configuración y no debe filtrarse.
- El `release` responde de inmediato, así que `ProxyTimeout` no es crítico.

### 9.6 Logs

Una línea JSON por registro a stdout (journald):

```json
{"ts": "2026-10-05T14:02:11.120+00:00", "level": "INFO", "logger": "lease",
 "message": "lease transition FREE -> LOCKED (acquire)", "event": "lease_transition",
 "from_state": "FREE", "to_state": "LOCKED", "reason": "acquire", "user_id": "40722571", "epoch": 12}
```

| Logger | Qué registra |
|---|---|
| `lease` | Cada transición (`event=lease_transition`), fallas de `safe_state` con traceback, errores del watchdog. |
| `hardware` | Pasos de respaldo de `safe_state`. |
| `lease.history` | Fallas de escritura, huérfanos cerrados, registros descartados. |
| `gunicorn.*` | Formato propio (no JSON). |

```bash
journalctl -u labrem -f -o cat
journalctl -u labrem -o cat | jq 'select(.event=="lease_transition")'
journalctl -u labrem -o cat | jq 'select(.to_state=="FAULT")'
```

`user_id` es el DNI, así que los logs contienen datos personales. Para no desgastar la SD se recomienda `Storage=volatile` en `/etc/systemd/journald.conf`.

### 9.7 Base de datos

Antes del primer despliegue se ejecuta `migrations/001_lease.sql`. Agrega la columna `role` a la tabla de usuarios (asumida `user`; verificar con `SHOW TABLES`) y crea `lease_history`. Después se asignan los administradores:

```sql
UPDATE `user` SET role = 'admin' WHERE username IN ('...');
```

Si `lease_history` no existe, el servidor funciona igual: el historial queda en memoria y se registran advertencias.

### 9.8 Lista de verificación

1. Ejecutar `migrations/001_lease.sql` y asignar administradores.
2. Configurar el cron PHP con `migrations/purge_lease_history.sql`.
3. Crear `.env` desde `.env.example` con los secretos de producción.
4. `pip install -r requirements.txt` en un virtualenv.
5. Instalar `deploy/labrem.service` y verificarla con `systemd-analyze verify`.
6. `curl -i http://localhost/healthz` debe responder `200` con estado `FREE` tras el reset inicial.

### 9.9 Guía de operación

| Síntoma | Diagnóstico | Acción |
|---|---|---|
| `/healthz` → `503` (`FAULT`) | `safe_state` falló; hay reintentos cada 30 s como máximo. | Revisar el prototipo (alimentación, Wi-Fi de los micros, broker) y los logs `to_state=FAULT` y `hardware`. Forzar un reintento con `force-release`. |
| Ocupado, pero el usuario dice no estar usándolo | Otra pestaña sigue enviando heartbeats, o todavía no venció. | Esperar ≤ 80 s desde que cerró la pestaña; si no, `force-release`. |
| `423` persistente con `10` s | El reset está esperando a la base o en el respaldo `com6`. | Logs `hardware`; si termina en `FAULT`, ver arriba. |
| Reinicios en bucle con `ProcessLockError` | Hay otro proceso del backend corriendo. | `ps aux \| grep gunicorn` y detener el sobrante. |
| `history.pending` crece | La base no acepta escrituras. | Logs `lease.history`. El laboratorio no se ve afectado. |
| El video no carga | Ticket inválido o lease terminado. | El frontend debe usar el `stream_token` vigente. |

---

## 10. Pruebas

### 10.1 Estrategia

La suite (`tests/`, **189 pruebas**, unos 4 s) verifica el comportamiento **sin hardware, sin red, sin MySQL y sin esperar tiempo real**. Lo hace reemplazando cada dependencia externa por un doble de prueba:

| Dependencia | Doble |
|---|---|
| Paso del tiempo | `FakeClock`: el tiempo avanza solo con `advance(segundos)`, así un vencimiento de 15 min se prueba en microsegundos. |
| Prototipo | `FakeDriver`: cuenta llamadas, simula fallas y puede quedar colgado hasta que el test lo libere. |
| Módulo `LabRem` | `FakeLabRem` / `RoutesLabRem`: estados de la base, comandos exitosos, rechazados o con timeout, gráficos. |
| Webcam | `FakeReader`: frames infinitos; registra si se cerró. |
| MySQL | `FakeHistoryStore` (con fallas simulables) y SQLite real para el store SQL. |
| Hilos de reset | `inline_runner`: reset en el mismo hilo, para tests deterministas. Un conjunto específico usa los hilos reales. |

Las pruebas de API usan el cliente de pruebas de Flask sobre una mini-aplicación armada con los mismos componentes que producción. `test_app_smoke.py` importa el **`app.py` real**, reemplazando solo `LabRem` y la base de datos.

```bash
cd Server
pip install -r requirements-dev.txt
python -m pytest -q
```

### 10.2 Suites

| Archivo | # | Qué verifica |
|---|---:|---|
| `unit/test_lease_manager.py` | 45 | Emisión, ocupado, 20 `acquire` concurrentes, límite duro, watchdog, chequeo perezoso, tokens viejos, `safe_state` único por cada causa de fin, `FAULT`, revocación antes del hardware, eventos de auditoría. |
| `unit/test_async_reset.py` | 9 | Con hilos reales: ninguna terminación espera al hardware; `stop()` espera un reset en curso y es idempotente. |
| `unit/test_hardware_fencing.py` | 12 | Fencing, la carrera comando contra expiración, comandos encolados, timeout del `io_lock`. |
| `unit/test_labrem_driver.py` | 8 | Secuencia de `safe_state`, respaldo con `com6`, idempotencia. |
| `unit/test_history.py` | 9 | Ciclo del registro, base caída y recuperación, límite de memoria, huérfanos, `record` que no bloquea. |
| `unit/test_process_lock.py` | 7 | Segundo proceso rechazado, liberación, guard desactivado. |
| `unit/test_logging_config.py` | 5 | JSON válido, campos de las transiciones. |
| `unit/test_gunicorn_conf.py` | 3 | `workers == 1` aunque se intente cambiar; defaults. |
| `unit/test_settings.py` | 2 | Defaults y lectura del entorno. |
| `api/test_lease_api.py` | 30 | Contrato de `/resource/*` y `force-release`: códigos, cuerpos, `Retry-After`, `reason`, release por header, JSON y `text/plain`. |
| `api/test_hardware_routes.py` | 34 | Cada endpoint exige lease; `E01`/`E02`/`E03`; gráficos; fencing por HTTP; cámara. |
| `api/test_history_sql.py` | 10 | Store sobre SQLite, endpoint de historial, una base caída no afecta al laboratorio. |
| `api/test_async_release_and_health.py` | 7 | `release` inmediato con el hardware ocupado; `/healthz`. |
| `api/test_app_smoke.py` | 8 | `app.py` real: login, lease, hardware, rol desde la base, endpoints viejos eliminados, historial, lock de proceso. |

### 10.3 Trazabilidad

| Requisito | Pruebas |
|---|---|
| RF1 | `test_concurrent_acquires_exactly_one_wins` |
| RF2 | `test_heartbeats_do_not_extend_the_hard_limit` |
| RF3 | `test_safe_state_called_exactly_once_per_session_end` (una por causa) |
| RF4 | `test_every_hardware_endpoint_requires_a_lease`, `test_jwt_alone_is_not_enough_for_hardware` |
| RF5, RF6 | `test_status_*`, `test_acquire_other_user_423_with_retry_after` |
| RNF1 | `test_no_heartbeat_watchdog_releases_after_timeout` |
| RNF2 | `test_race_inflight_command_vs_expiry`, `test_inflight_command_blocks_safe_state_and_next_request_is_revoked` |
| RNF3 | `test_start_with_initial_reset_runs_safe_state_in_background` |
| RNF5 | `test_healthz_503_when_fault` |

### 10.4 Fuera de la suite

Requieren la Raspberry y el prototipo: MQTT real y comportamiento del firmware, gunicorn y systemd en ejecución (incluido `atexit` tras `SIGTERM`), la rama `fcntl` del lock (la suite corrió en Windows), MySQL real (se usa SQLite con construcciones portables), el proxy de Apache, la webcam y el frontend.

---

## 11. Decisiones de arquitectura

| # | Decisión | Contexto y motivo | Alternativa descartada |
|---|---|---|---|
| 1 | **Separar identidad (JWT) de acceso (lease).** | El JWT usado como lock no detectaba desconexiones, y un temporizador independiente podía liberar una sesión ajena. | Agregar heartbeat al JWT: mezcla dos ciclos de vida y no permite revocar el acceso sin invalidar la identidad. |
| 2 | **Estado en memoria, un único proceso.** | Un prototipo, demanda baja, una Raspberry. | Redis: un servicio más que operar, sin beneficio. |
| 3 | **Relojes monotónicos.** | La Raspberry no tiene reloj con batería; NTP puede saltar la hora. | Reloj de pared. |
| 4 | **Watchdog + chequeo perezoso.** | Sin watchdog, un lease abandonado viviría mientras no haya tráfico. | Solo chequeo perezoso. |
| 5 | **Límite duro no renovable; heartbeat 20/75 s.** | Throttling de timers en pestañas en segundo plano. | 30/45 s: perdería sesiones con la pestaña de fondo. |
| 6 | **Re-acquire idempotente.** | Recuperar la sesión tras recargar la página. | Rechazar: obliga a esperar el vencimiento. |
| 7 | **`FAULT` bloqueante.** | Entregar hardware en estado desconocido es peor que negar el servicio. | Liberar igual y registrar el error. |
| 8 | **Fencing por época con `io_lock`.** | Un comando validado puede llegar tarde al hardware. | Validar solo al inicio del request. |
| 9 | **`safe_state` fuera del lock y asíncrono.** | Puede tardar más de un minuto y medio; bloquearía heartbeats y chocaría con el proxy. | Reset dentro del request. |
| 10 | **Flask con hilos.** | Todo el hardware es bloqueante; el código existente es Flask. | Migrar a FastAPI: reescritura completa sin beneficio. |
| 11 | **Ticket de cámara separado.** | El video necesita la credencial en la URL. | Usar el lease token en la URL. |
| 12 | **Resultados solo durante el lease.** | Las mediciones son globales y se sobrescriben. | Persistir por sesión (trabajo futuro). |
| 13 | **Esperar el comando en vuelo.** | Los comandos MQTT no se pueden abortar. | Abortar: no es posible en el firmware. |
| 14 | **Reset de arranque en segundo plano.** | Un reset bloqueante podría superar el arranque de gunicorn y ocultar fallas en un bucle de reinicios. | Reset bloqueante al importar. |
| 15 | **Historial en MySQL con respaldo en memoria.** | La base es remota; la SD no tolera escrituras frecuentes. | Archivo local de respaldo. |
| 16 | **Purga externa, 7 días.** | Retención ajustable sin desplegar el backend. | Purga desde el servidor. |
| 17 | **Polling en lugar de WebSocket.** | Cada conexión ocuparía un hilo; Apache requeriría `mod_proxy_wstunnel`; un F5 cortaría la señal. | WebSocket o SSE. |
| 18 | **gunicorn 1 worker, 6 hilos.** | Margen para el polling y para que el endpoint de rescate siempre responda. | 4 hilos: un solo hilo libre. |
| 19 | **Rol de admin en la base, consultado por request.** | Un rol revocado deja de valer al instante. | Claim en el JWT: seguiría vigente hasta vencer. |
| 20 | **Secretos en `.env`.** | Estaban escritos en el código. | — |
| 21 | **Dependencias inyectables.** | Reloj, driver, `LabRem`, cámara, store y ejecutor de resets se reciben por parámetro: lógica testeable sin hardware ni tiempo real. | Dependencias globales. |

---

## 12. Limitaciones y deuda técnica

### 12.1 Validaciones pendientes en el prototipo

| # | Verificación | Resultado esperado |
|---|---|---|
| 1 | `com4` desde `ESPERANDO COMANDO`, y rampa en 0° tras `com6`. | `safe_state` termina bien tras un reset de micros. |
| 2 | Cerrar la pestaña durante un experimento. | Liberación en ≤ 90 s y `safe_state` ejecutado. |
| 3 | `kill -9` durante una sesión. | `safe_state` de arranque, sesión cerrada como `server_restart`, el cliente recibe `401`. |
| 4 | Cortar la red del cliente. | Liberación por `heartbeat_timeout`. |
| 5 | Pestaña en segundo plano 10 min. | La sesión no se pierde. |
| 6 | Dos usuarios piden el lease a la vez. | Uno recibe `200` y el otro `423`. |
| 7 | Liberación con un comando largo en vuelo. | `safe_state` espera; no se ejecuta ningún comando posterior. |
| 8 | Falla simulada de `safe_state`. | `FAULT`, `503` en `acquire` y `/healthz`, reintentos en los logs. |
| 9 | 15 min con heartbeat constante. | La sesión se corta igual. |
| 10 | `systemctl stop` con una sesión activa. | `safe_state` ejecutado. Si `atexit` no corre bajo gunicorn, agregar un hook `worker_exit`. |
| 11 | Segundo proceso del backend. | `ProcessLockError` inmediato. |
| 12 | Video a través de Apache con gunicorn. | Stream fluido que se corta al terminar la sesión. |

### 12.2 Seguridad

| Problema | Impacto | Mitigación posible |
|---|---|---|
| `POST /` emite un JWT a cualquiera que conozca un DNI registrado; la sesión PHP solo se valida en el frontend. | Cualquiera puede obtener una identidad y pedir el laboratorio. | Validar la sesión en el servidor (consultar al PHP con la cookie, o un token firmado por el PHP). |
| Los secretos estuvieron escritos en el código en versiones anteriores. | Visibles en el historial de git. | Rotar la clave del JWT y la contraseña de MySQL. |
| El backend es accesible en `10.150.0.102:80` sin pasar por Apache. | Se puede eludir Apache (impacto bajo). | Firewall que permita solo a Apache; restringir `CORS_ORIGINS`. |
| No hay logout: `TokenBlocklist` nunca se escribe. | Un JWT no se puede revocar antes de 1 h. | Endpoint de logout. |
| El DNI aparece en logs e historial. | Datos personales. | Retención acotada; journald en memoria. |

### 12.3 Limitaciones funcionales

- **Resultados no persistidos:** si la sesión termina antes de descargarlos, se pierden.
- **Sin cola de espera:** quien encuentra el laboratorio ocupado recibe `423` y debe reintentar.
- **Dos pestañas, una sesión:** consecuencia del re-acquire idempotente.
- **Estimaciones aproximadas:** en `LOCKED` el tiempo es una cota superior; en `RESETTING` es una estimación fija de 10 s.
- **Gráficos antes del primer experimento:** responden `500`.
- **Historial volátil:** se pierde si el proceso muere mientras la base está caída.

### 12.4 Deuda heredada de `LabRem.py`

- Estado global compartido con el hilo MQTT, sin sincronizar con el `io_lock`.
- `iniExp()` retorna antes de tiempo (acepta cualquier estado "lista"); la espera fija de 5 s cubre el experimento.
- Cada consulta de estado publica `com5` y duerme 0,2 s.
- Broker y posición de los sensores fijos en el código.
- `app_local.py` conserva el mecanismo anterior y no se mantiene.

### 12.5 Trabajo futuro

Cliente del lease en el frontend React; validación de identidad en el servidor; resultados por sesión; cola o reservas; estado compartido si alguna vez hiciera falta más de un proceso; métricas.

---

## 13. Glosario

| Término | Significado |
|---|---|
| **Lease** | Permiso temporal y exclusivo para operar el hardware, con límite duro y heartbeat. |
| **Lease token** | Secreto que prueba la titularidad del lease (`X-Lease-Token`). |
| **Stream token** | Secreto que solo autoriza la cámara. |
| **Heartbeat** | Señal periódica de presencia del cliente. |
| **Época** | Entero que se incrementa con cada lease; identifica la sesión para el fencing. |
| **Fencing** | Técnica que impide que una operación de una sesión terminada llegue al recurso. |
| **`safe_state`** | Secuencia que lleva el prototipo a la rampa en 0°. |
| **`FAULT`** | Estado en que `safe_state` falló; el recurso no se entrega. |
| **Watchdog** | Hilo que revisa periódicamente el vencimiento del lease. |
| **Chequeo perezoso** | Verificación de vencimiento al recibir un request. |
| **`lease_id`** | UUID de cada lease, clave del historial. |
| **Base / Móvil** | Microcontroladores de la rampa y del carro. |
