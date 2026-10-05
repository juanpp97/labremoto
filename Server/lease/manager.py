import logging
import math
import secrets
import threading
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from .clock import Clock
from .errors import LeaseInvalid, ResourceBusy, ResourceFault
from .models import EndReason, LeaseContext, LeaseGrant, LeaseState, StatusSnapshot

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

        self._lock = threading.Lock()
        self._state = LeaseState.FREE
        self._token: Optional[str] = None
        self._stream_token: Optional[str] = None
        self._user_id: Optional[str] = None
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
        self._finish_reset()
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
        self._finish_reset()
        if expired is not None:
            raise LeaseInvalid(expired)

    def force_release(self, reason: EndReason = EndReason.FORCED) -> bool:
        """Termina el lease activo, o reintenta safe_state si está en FAULT."""
        with self._lock:
            if self._state is LeaseState.LOCKED:
                self._begin_reset_locked(reason)
                retry = False
            elif self._state is LeaseState.FAULT:
                retry = True
            else:
                return False
        if retry:
            self.retry_safe_state()
        else:
            self._finish_reset()
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
        self._finish_reset()

    def retry_safe_state(self) -> LeaseState:
        """Reintenta safe_state si el recurso está en FAULT."""
        with self._lock:
            if self._state is not LeaseState.FAULT:
                return self._state
            self._set_state_locked(LeaseState.RESETTING, "retry")
        self._finish_reset()
        with self._lock:
            return self._state

    def start(self) -> None:
        if self._watchdog_thread is not None:
            return
        self._stop_event.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="lease-watchdog", daemon=True
        )
        self._watchdog_thread.start()

    def stop(self) -> None:
        """Shutdown: detiene hilos y deja el hardware en estado seguro."""
        self._stop_event.set()
        for thread in (self._watchdog_thread, self._retry_thread):
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
            self._finish_reset()
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
            "lease transition from_state=%s to_state=%s reason=%s user_id=%s epoch=%s",
            self._state.value, new_state.value, reason, self._user_id, self._epoch,
        )
        self._state = new_state

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
            self._set_state_locked(LeaseState.LOCKED, "acquire")
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
        self._finish_reset()
        # Lo que venció es el lease vigente; su token ya no sirve.
        with self._lock:
            raise LeaseInvalid(self._reason_for_locked(token))

    def _begin_reset_locked(self, reason: EndReason) -> None:
        self._last_ended_token = self._token
        self._last_end_reason = reason
        self._set_state_locked(LeaseState.RESETTING, reason.value)
        # El token se invalida acá, antes de tocar el hardware.
        self._token = None
        self._stream_token = None
        self._user_id = None

    def _finish_reset(self) -> None:
        """Ejecuta safe_state fuera del lock; RESETTING -> FREE o FAULT."""
        try:
            self._hardware.safe_state()
        except Exception:
            logger.exception("safe_state falló; el recurso pasa a FAULT")
            with self._lock:
                self._set_state_locked(LeaseState.FAULT, "safe_state_failed")
                self._ensure_retry_thread_locked()
            return
        with self._lock:
            self._set_state_locked(LeaseState.FREE, "safe_state_ok")

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
