from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class LeaseState(str, Enum):
    FREE = "FREE"
    LOCKED = "LOCKED"
    RESETTING = "RESETTING"
    FAULT = "FAULT"


class EndReason(str, Enum):
    EXPIRED = "expired"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    RELEASED = "released"
    FORCED = "forced"
    SERVER_SHUTDOWN = "server_shutdown"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LeaseContext:
    token: str
    epoch: int


@dataclass(frozen=True)
class LeaseGrant:
    lease_token: str
    stream_token: str
    epoch: int
    expires_in: int
    heartbeat_every: int
    heartbeat_timeout: int


@dataclass(frozen=True)
class StatusSnapshot:
    state: LeaseState
    available: bool
    available_in_seconds: Optional[int]


class EventKind(str, Enum):
    STARTED = "started"
    ENDED = "ended"
    RESET_DONE = "reset_done"


@dataclass(frozen=True)
class LeaseEvent:
    """Evento del ciclo de vida de un lease, para auditoría. at_utc es reloj de pared."""

    kind: EventKind
    lease_id: str
    at_utc: datetime
    user_id: Optional[str] = None
    end_reason: Optional[EndReason] = None
    safe_state_ok: Optional[bool] = None
    safe_state_ms: Optional[int] = None
