from dataclasses import dataclass
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
