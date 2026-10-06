import logging
import math
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from .clock import Clock
from .errors import LeaseInvalid, ResourceBusy, ResourceFault
from .models import (
    EndReason,
    EventKind,
    LeaseContext,
    LeaseEvent,
    LeaseGrant,
    LeaseState,
    StatusSnapshot,
)

logger = logging.getLogger("lease")


class SafeStateHardware(Protocol):
    def safe_state(self) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _same(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return secrets.compare_digest(a.encode(), b.encode())


class LeaseManager:
    """Lease de acceso exclusivo sobre el hardware.

    Reglas de concurrencia:
    - Todo el estado se muta bajo `_lock`.
    - safe_state() NUNCA se ejecuta con `_lock` tomado (puede tardar y bloquearía
      heartbeats). Se hace la transición a RESETTING bajo lock, se suelta, y
      recién entonces se llama al hardware (`_finish_reset`).
    - Todos los deadlines usan el Clock monotónico; el reloj de pared solo se
      guarda en `acquired_at_utc` para auditoría.
    """

    def __init__(
        self,
        hardware: SafeStateHardware,
        clock: Clock,
        lease_duration: int = 900,
        heartbeat_every: int = 20,
        heartbeat_timeout: int = 75,
        watchdog_tick: float = 5,
        retry_initial: float = 2,
        retry_max: float = 30,
        reset_estimate: int = 10,
        wall_clock: Callable[[], datetime] = _utc_now,
        on_event: Optional[Callable[[LeaseEvent], None]] = None,
        reset_runner: Optional[Callable[[Callable[[], None]], None]] = None,
    ):
        if not 0 < heartbeat_every < heartbeat_timeout < lease_duration:
            raise ValueError("se requiere 0 < heartbeat_every < heartbeat_timeout < lease_duration")
        self._hardware = hardware
        self._clock = clock
        self._lease_duration = lease_duration
        self._heartbeat_every = heartbeat_every
        self._heartbeat_timeout = heartbeat_timeout
        self._watchdog_tick = watchdog_tick
        self._retry_initial = retry_initial
        self._retry_max = retry_max
        self._reset_estimate = reset_estimate
        self._wall_clock = wall_clock
        # Observer de auditoría: se invoca con el lock tomado (orden garantizado),
        # por eso NO debe bloquear ni lanzar (si lanza, se loguea y se ignora).
        self._on_event = on_event
        # Cómo se ejecuta el safe_state tras terminar un lease. Por defecto en un hilo
        # propio (los requests no esperan al hardware); los tests inyectan uno en línea.
        self._reset_runner = reset_runner

        self._lock = threading.Lock()
        self._state = LeaseState.FREE
        self._token: Optional[str] = None
        self._stream_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._lease_id: Optional[str] = None
        self._resetting_lease_id: Optional[str] = None
        self._epoch = 0
        self._expires_at = 0.0
        self._last_heartbeat = 0.0
        self._acquired_at_utc: Optional[datetime] = None
        # Solo se recuerda el último lease terminado (para el `reason` del 401).
        self._last_ended_token: Optional[str] = None
        self._last_end_reason = EndReason.UNKNOWN

        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._retry_thread: Optional[threading.Thread] = None
        self._startup_thread: Optional[threading.Thread] = None
        self._reset_thread: Optional[threading.Thread] = None
        self._stopped = False

    # ------------------------------------------------------------------ props
    @property
    def lease_duration(self) -> int:
        return self._lease_duration

    @property
    def heartbeat_every(self) -> int:
        return self._heartbeat_every

    @property
    def heartbeat_timeout(self) -> int:
        return self._heartbeat_timeout

    # -------------------------------------------------------------- public API
    def acquire(self, user_id: str) -> LeaseGrant:
        with self._lock:
            reason = self._expire_reason_locked()
            if reason is None:
                return self._acquire_locked(user_id)
            self._begin_reset_locked(reason)
        self._schedule_reset()
        with self._lock:
            return self._acquire_locked(user_id)

    def renew(self, token: Optional[str]) -> int:
        """Heartbeat. Devuelve segundos restantes; nunca extiende expires_at."""
        _, remaining = self._check(token, touch=True)
        return remaining

    def validate(self, token: Optional[str]) -> LeaseContext:
        """Valida el token; cuenta como señal de vida."""
        ctx, _ = self._check(token, touch=True)
        return ctx

    def validate_stream(self, stream_token: Optional[str]) -> int:
        """Valida el ticket de cámara. No cuenta como heartbeat. Devuelve el epoch."""
        with self._lock:
            if (
                self._state is LeaseState.LOCKED
                and self._expire_reason_locked() is None
                and _same(stream_token, self._stream_token)
            ):
                return self._epoch
            raise LeaseInvalid(self._reason_for_locked(stream_token))

    def is_current(self, epoch: int) -> bool:
        """Chequeo puro (sin transiciones) para el fencing del hardware."""
        with self._lock:
            return (
                self._state is LeaseState.LOCKED
                and epoch == self._epoch
                and self._expire_reason_locked() is None
            )

    def release(self, token: Optional[str]) -> None:
        with self._lock:
            reason = self._expire_reason_locked()
            if reason is None:
                self._authenticate_locked(token, touch=False)
                self._begin_reset_locked(EndReason.RELEASED)
                expired = None
            else:
                self._begin_reset_locked(reason)
                expired = reason
        self._schedule_reset()
        if expired is not None:
            raise LeaseInvalid(expired)

    def force_release(self, reason: EndReason = EndReason.FORCED) -> bool:
        """Termina el lease activo, o reintenta safe_state si está en FAULT.

        Retorna sin esperar al hardware: el reset corre en segundo plano.
        """
        with self._lock:
            if self._state is LeaseState.LOCKED:
                self._begin_reset_locked(reason)
            elif self._state is LeaseState.FAULT:
                self._set_state_locked(LeaseState.RESETTING, "force_retry")
            else:
                return False
        self._schedule_reset()
        return True

    def status(self) -> StatusSnapshot:
        """Solo lectura. No expone el user_id del ocupante."""
        with self._lock:
            state = self._state
            if state is LeaseState.FREE:
                return StatusSnapshot(state, True, 0)
            if state is LeaseState.LOCKED:
                return StatusSnapshot(state, False, self._remaining_locked())
            if state is LeaseState.RESETTING:
                return StatusSnapshot(state, False, self._reset_estimate)
            return StatusSnapshot(state, False, None)

    def tick(self) -> None:
        """Una pasada del watchdog: libera si venció el límite o faltó heartbeat."""
        with self._lock:
            reason = self._expire_reason_locked()
            if reason is None:
                return
            self._begin_reset_locked(reason)
        self._schedule_reset()

    def retry_safe_state(self) -> LeaseState:
        """Reintenta safe_state si el recurso está en FAULT."""
        with self._lock:
            if self._state is not LeaseState.FAULT:
                return self._state
            self._set_state_locked(LeaseState.RESETTING, "retry")
        self._finish_reset()
        with self._lock:
            return self._state

    def reason_for(self, token: Optional[str]) -> EndReason:
        """Motivo de fin si `token` es el del último lease terminado; si no, UNKNOWN."""
        with self._lock:
            return self._reason_for_locked(token)

    def start(self, initial_reset: bool = False) -> None:
        """Arranca el watchdog. Con initial_reset, el recurso nace en RESETTING y un
        hilo ejecuta safe_state (RNF3) sin bloquear el arranque del servidor."""
        if self._watchdog_thread is not None:
            return
        self._stop_event.clear()
        self._stopped = False
        if initial_reset:
            with self._lock:
                self._set_state_locked(LeaseState.RESETTING, "startup")
            self._startup_thread = threading.Thread(
                target=self._finish_reset, name="lease-startup-reset", daemon=True
            )
            self._startup_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="lease-watchdog", daemon=True
        )
        self._watchdog_thread.start()

    def stop(self) -> None:
        """Shutdown: detiene hilos y deja el hardware en estado seguro. Idempotente."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self._stop_event.set()
        threads = (self._startup_thread, self._reset_thread, self._watchdog_thread, self._retry_thread)
        for thread in threads:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=30)
        self._watchdog_thread = None
        with self._lock:
            if self._state is LeaseState.LOCKED:
                self._begin_reset_locked(EndReason.SERVER_SHUTDOWN)
                locked = True
            else:
                locked = False
        if locked:
            self._finish_reset()  # en el apagado sí se espera al hardware
            return
        try:
            self._hardware.safe_state()
        except Exception:
            logger.exception("safe_state falló durante el shutdown")

    # ---------------------------------------------------------------- internal
    def _now(self) -> float:
        return self._clock.now()

    def _remaining_locked(self) -> int:
        return max(0, math.ceil(self._expires_at - self._now()))

    def _expire_reason_locked(self) -> Optional[EndReason]:
        if self._state is not LeaseState.LOCKED:
            return None
        now = self._now()
        if now >= self._expires_at:
            return EndReason.EXPIRED
        if now - self._last_heartbeat > self._heartbeat_timeout:
            return EndReason.HEARTBEAT_TIMEOUT
        return None

    def _set_state_locked(self, new_state: LeaseState, reason: str) -> None:
        logger.info(
            "lease transition %s -> %s (%s)", self._state.value, new_state.value, reason,
            extra={
                "event": "lease_transition",
                "from_state": self._state.value,
                "to_state": new_state.value,
                "reason": reason,
                "user_id": self._user_id,
                "epoch": self._epoch,
            },
        )
        self._state = new_state

    def _emit_locked(self, event: LeaseEvent) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            logger.exception("el observer de eventos de lease falló; se ignora")

    def _grant_locked(self) -> LeaseGrant:
        return LeaseGrant(
            lease_token=self._token,
            stream_token=self._stream_token,
            epoch=self._epoch,
            expires_in=self._remaining_locked(),
            heartbeat_every=self._heartbeat_every,
            heartbeat_timeout=self._heartbeat_timeout,
        )

    def _acquire_locked(self, user_id: str) -> LeaseGrant:
        state = self._state
        if state is LeaseState.FREE:
            now = self._now()
            self._epoch += 1
            self._token = secrets.token_urlsafe(32)
            self._stream_token = secrets.token_urlsafe(32)
            self._user_id = user_id
            self._expires_at = now + self._lease_duration
            self._last_heartbeat = now
            self._acquired_at_utc = self._wall_clock()
            self._lease_id = str(uuid.uuid4())
            self._set_state_locked(LeaseState.LOCKED, "acquire")
            self._emit_locked(
                LeaseEvent(EventKind.STARTED, self._lease_id, self._acquired_at_utc, user_id=user_id)
            )
            return self._grant_locked()
        if state is LeaseState.LOCKED:
            if user_id == self._user_id:
                # Re-acquire idempotente (ej. F5): devuelve el lease vigente.
                self._last_heartbeat = self._now()
                return self._grant_locked()
            raise ResourceBusy(self._remaining_locked())
        if state is LeaseState.RESETTING:
            raise ResourceBusy(self._reset_estimate)
        raise ResourceFault()

    def _reason_for_locked(self, token: Optional[str]) -> EndReason:
        if _same(token, self._last_ended_token):
            return self._last_end_reason
        return EndReason.UNKNOWN

    def _authenticate_locked(self, token: Optional[str], touch: bool) -> LeaseContext:
        if self._state is LeaseState.LOCKED and _same(token, self._token):
            if touch:
                self._last_heartbeat = self._now()
            return LeaseContext(self._token, self._epoch)
        raise LeaseInvalid(self._reason_for_locked(token))

    def _check(self, token: Optional[str], touch: bool):
        with self._lock:
            reason = self._expire_reason_locked()
            if reason is None:
                ctx = self._authenticate_locked(token, touch)
                return ctx, self._remaining_locked()
            self._begin_reset_locked(reason)
        self._schedule_reset()
        # Lo que venció es el lease vigente; su token ya no sirve.
        with self._lock:
            raise LeaseInvalid(self._reason_for_locked(token))

    def _begin_reset_locked(self, reason: EndReason) -> None:
        self._last_ended_token = self._token
        self._last_end_reason = reason
        self._resetting_lease_id = self._lease_id
        if self._lease_id is not None:
            self._emit_locked(
                LeaseEvent(
                    EventKind.ENDED, self._lease_id, self._wall_clock(),
                    user_id=self._user_id, end_reason=reason,
                )
            )
        self._set_state_locked(LeaseState.RESETTING, reason.value)
        # El token se invalida acá, antes de tocar el hardware.
        self._token = None
        self._stream_token = None
        self._user_id = None
        self._lease_id = None

    def _schedule_reset(self) -> None:
        """Lanza safe_state (RESETTING -> FREE/FAULT) sin bloquear a quien llama."""
        if self._reset_runner is not None:
            self._reset_runner(self._finish_reset)
            return
        thread = threading.Thread(target=self._finish_reset, name="lease-reset", daemon=True)
        self._reset_thread = thread
        thread.start()

    def _finish_reset(self) -> None:
        """Ejecuta safe_state fuera del lock; RESETTING -> FREE o FAULT."""
        started = self._now()
        try:
            self._hardware.safe_state()
        except Exception:
            logger.exception("safe_state falló; el recurso pasa a FAULT")
            with self._lock:
                self._emit_reset_done_locked(False, started)
                self._set_state_locked(LeaseState.FAULT, "safe_state_failed")
                self._ensure_retry_thread_locked()
            return
        with self._lock:
            self._emit_reset_done_locked(True, started)
            self._resetting_lease_id = None
            self._set_state_locked(LeaseState.FREE, "safe_state_ok")

    def _emit_reset_done_locked(self, ok: bool, started: float) -> None:
        if self._resetting_lease_id is None:  # reset de arranque: no hay lease asociado
            return
        self._emit_locked(
            LeaseEvent(
                EventKind.RESET_DONE, self._resetting_lease_id, self._wall_clock(),
                safe_state_ok=ok, safe_state_ms=int((self._now() - started) * 1000),
            )
        )

    def _ensure_retry_thread_locked(self) -> None:
        if self._retry_thread is not None or self._stop_event.is_set():
            return
        self._retry_thread = threading.Thread(
            target=self._retry_loop, name="lease-safe-state-retry", daemon=True
        )
        self._retry_thread.start()

    def _retry_loop(self) -> None:
        delay = self._retry_initial
        while not self._stop_event.wait(delay):
            with self._lock:
                if self._state is not LeaseState.FAULT:
                    self._retry_thread = None
                    return
            try:
                self.retry_safe_state()
            except Exception:
                logger.exception("error inesperado en el reintento de safe_state")
            with self._lock:
                if self._state is not LeaseState.FAULT:
                    self._retry_thread = None
                    return
            delay = min(delay * 2, self._retry_max)
        with self._lock:
            self._retry_thread = None

    def _watchdog_loop(self) -> None:
        # Nunca debe morir: si muere en silencio se pierde la garantía de liberación.
        while not self._stop_event.wait(self._watchdog_tick):
            try:
                self.tick()
            except Exception:
                logger.exception("error en el watchdog; se continúa")
