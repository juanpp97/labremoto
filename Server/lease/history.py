import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Protocol

from .models import EventKind, LeaseEvent

logger = logging.getLogger("lease.history")


class HistoryStore(Protocol):
    def upsert(self, record: dict) -> None:
        """Inserta o actualiza (idempotente) el registro completo de un lease."""
        ...

    def close_orphans(self, before: datetime, ended_at: datetime) -> int:
        """Cierra los leases abiertos anteriores a `before` (motivo server_restart)."""
        ...

    def recent(self, limit: int) -> List[dict]: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_record(record: dict) -> dict:
    """Registro -> dict JSON-friendly (fechas ISO-8601 en UTC)."""
    out = dict(record)
    for key in ("acquired_at", "ended_at"):
        value = out.get(key)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            out[key] = value.astimezone(timezone.utc).isoformat()
    return out


class HistoryRecorder:
    """Persiste el historial de leases sin poner a la DB en el camino crítico.

    - record() es O(1) y no bloquea: solo actualiza un registro en memoria.
    - Un hilo escritor hace upsert idempotente del registro completo. Si la DB falla,
      el registro queda en memoria y se reintenta con backoff (no se escribe a disco:
      evita desgaste de la SD de la Raspberry). Se pierde si el proceso muere.
    - Memoria acotada: sobre `max_pending` registros sin persistir se descarta el más
      viejo ya terminado y se cuenta en `dropped_count`.
    """

    def __init__(
        self,
        store: HistoryStore,
        max_pending: int = 1000,
        retry_initial: float = 5.0,
        retry_max: float = 60.0,
        wall_clock: Callable[[], datetime] = _utc_now,
        boot_time: Optional[datetime] = None,
    ):
        self._store = store
        self._max_pending = max_pending
        self._retry_initial = retry_initial
        self._retry_max = retry_max
        self._wall_clock = wall_clock
        self._boot_time = boot_time or wall_clock()

        self._lock = threading.Lock()
        self._records: Dict[str, dict] = {}
        self._dirty: Dict[str, int] = {}  # lease_id -> secuencia de la última modificación
        self._seq = 0
        self._dropped = 0

        self._orphans_closed = False
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------- public API
    @property
    def dropped_count(self) -> int:
        return self._dropped

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._dirty)

    def pending_records(self) -> List[dict]:
        """Copia de los registros todavía no persistidos (para lectura)."""
        with self._lock:
            return [dict(self._records[i]) for i in self._dirty if i in self._records]

    def recent(self, limit: int) -> List[dict]:
        return self._store.recent(limit)

    def record(self, event: LeaseEvent) -> None:
        with self._lock:
            record = self._records.get(event.lease_id)
            if record is None:
                if event.kind is not EventKind.STARTED:
                    return  # lease desconocido (descartado por la cota): no se puede persistir
                record = {
                    "lease_id": event.lease_id, "username": None, "acquired_at": None,
                    "ended_at": None, "end_reason": None,
                    "safe_state_ok": None, "safe_state_ms": None,
                }
                self._records[event.lease_id] = record
            if event.kind is EventKind.STARTED:
                record["username"] = event.user_id
                record["acquired_at"] = event.at_utc
            elif event.kind is EventKind.ENDED:
                record["ended_at"] = event.at_utc
                record["end_reason"] = event.end_reason.value if event.end_reason else None
            else:
                record["safe_state_ok"] = event.safe_state_ok
                record["safe_state_ms"] = event.safe_state_ms
            self._seq += 1
            self._dirty[event.lease_id] = self._seq
            self._enforce_bound_locked()
        self._wake.set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="lease-history", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Detiene el hilo e intenta un último flush (best-effort)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        try:
            self._flush_once()
        except Exception:
            logger.exception("flush final del historial falló")

    # ---------------------------------------------------------------- internal
    def _enforce_bound_locked(self) -> None:
        while len(self._dirty) > self._max_pending:
            victim = next(
                (i for i in self._dirty if self._records[i]["ended_at"] is not None), None
            )
            if victim is None:
                return
            del self._dirty[victim]
            del self._records[victim]
            self._dropped += 1
            logger.warning("historial: memoria llena, se descarta el lease %s", victim)

    def _flush_once(self) -> bool:
        """Persiste lo pendiente. True si no hubo fallos."""
        with self._lock:
            pending = [
                (i, seq, dict(self._records[i]))
                for i, seq in self._dirty.items()
                if self._records[i]["acquired_at"] is not None
            ]
        for lease_id, seq, snapshot in pending:
            try:
                self._store.upsert(snapshot)
            except Exception as exc:
                logger.warning("historial: no se pudo escribir en la DB (%s); queda en memoria", exc)
                return False
            with self._lock:
                if self._dirty.get(lease_id) == seq:
                    del self._dirty[lease_id]
                    record = self._records[lease_id]
                    # Se conserva en memoria hasta que el safe_state termine bien: los
                    # reintentos de FAULT todavía pueden actualizar este registro.
                    if record["ended_at"] is not None and record["safe_state_ok"] is True:
                        del self._records[lease_id]
        return True

    def _run(self) -> None:
        delay = self._retry_initial
        while not self._stop.is_set():
            ok = True
            if not self._orphans_closed:
                try:
                    closed = self._store.close_orphans(self._boot_time, self._wall_clock())
                    self._orphans_closed = True
                    if closed:
                        logger.warning("historial: %s lease(s) huérfanos cerrados", closed)
                except Exception as exc:
                    logger.warning("historial: no se pudieron cerrar huérfanos (%s)", exc)
                    ok = False
            if ok:
                ok = self._flush_once()
            if ok:
                delay = self._retry_initial
                self._wake.wait()
                self._wake.clear()
            else:
                self._stop.wait(delay)
                delay = min(delay * 2, self._retry_max)
