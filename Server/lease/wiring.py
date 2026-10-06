import atexit
from typing import Callable, Optional

from hardware.controller import HardwareController, HardwareDriver

from .clock import Clock, MonotonicClock
from .flask_api import admin_bp, health_bp, register_error_handlers, resource_bp
from .history import HistoryRecorder
from .manager import LeaseManager
from .process_lock import acquire_process_lock
from .settings import LeaseSettings


def setup_resource(
    app,
    driver: HardwareDriver,
    settings: Optional[LeaseSettings] = None,
    is_admin: Callable[[str], bool] = lambda identity: False,
    clock: Optional[Clock] = None,
    register_atexit: bool = True,
    history_store=None,
    history_options: Optional[dict] = None,
    reset_runner=None,
    process_lock_path: Optional[str] = None,
):
    """Conecta el lease a una app Flask existente.

    Crea el HardwareController y el LeaseManager, registra los endpoints y los
    manejadores de error, y arranca el watchdog. El safe_state de arranque corre
    en un hilo: hasta que termine el recurso está en RESETTING (423).
    Requiere que la app ya tenga JWTManager configurado.

    Con `history_store` se registra el historial de leases (DB con fallback en memoria;
    ver lease/history.py). Una falla del historial nunca afecta al hardware ni al lease.

    Con `process_lock_path` se exige ser el único proceso (ProcessLockError si no): el
    estado del lease vive en memoria. `reset_runner` permite ejecutar los resets en línea
    (tests); por defecto corren en un hilo.
    """
    process_lock = acquire_process_lock(process_lock_path)  # antes de crear nada
    settings = settings or LeaseSettings.from_env()
    hardware = HardwareController(driver)
    recorder = None
    if history_store is not None:
        recorder = HistoryRecorder(history_store, **(history_options or {}))
    manager = LeaseManager(
        hardware,
        clock or MonotonicClock(),
        lease_duration=settings.lease_duration,
        heartbeat_every=settings.heartbeat_every,
        heartbeat_timeout=settings.heartbeat_timeout,
        watchdog_tick=settings.watchdog_tick,
        retry_initial=settings.safe_state_retry_initial,
        retry_max=settings.safe_state_retry_max,
        on_event=recorder.record if recorder else None,
        reset_runner=reset_runner,
    )
    hardware.attach_lease_checker(manager.is_current)

    app.extensions["lease_manager"] = manager
    app.extensions["lease_hardware"] = hardware
    app.extensions["lease_is_admin"] = is_admin
    app.extensions["lease_history"] = recorder
    app.extensions["lease_process_lock"] = process_lock
    register_error_handlers(app)
    app.register_blueprint(resource_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    if recorder is not None:
        recorder.start()
    manager.start(initial_reset=True)
    if register_atexit:
        # atexit es LIFO: primero se detiene el manager (emite los últimos eventos)
        # y después el recorder hace su flush final.
        if recorder is not None:
            atexit.register(recorder.stop)
        atexit.register(manager.stop)
    return manager, hardware
