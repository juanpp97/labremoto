from dataclasses import dataclass


@dataclass(frozen=True)
class LeaseSettings:
    lease_duration: int = 900
    heartbeat_every: int = 20
    heartbeat_timeout: int = 75
    watchdog_tick: float = 5
    safe_state_retry_initial: float = 2
    safe_state_retry_max: float = 30
    jwt_lifetime: int = 3600

    @classmethod
    def from_env(cls) -> "LeaseSettings":
        """Lee variables de entorno (o del archivo .env) con los defaults del plan."""
        from decouple import config

        d = cls()
        return cls(
            lease_duration=config("LEASE_DURATION_S", default=d.lease_duration, cast=int),
            heartbeat_every=config("HEARTBEAT_EVERY_S", default=d.heartbeat_every, cast=int),
            heartbeat_timeout=config("HEARTBEAT_TIMEOUT_S", default=d.heartbeat_timeout, cast=int),
            watchdog_tick=config("WATCHDOG_TICK_S", default=d.watchdog_tick, cast=float),
            safe_state_retry_initial=config(
                "SAFE_STATE_RETRY_INITIAL_S", default=d.safe_state_retry_initial, cast=float
            ),
            safe_state_retry_max=config(
                "SAFE_STATE_RETRY_MAX_S", default=d.safe_state_retry_max, cast=float
            ),
            jwt_lifetime=config("JWT_LIFETIME_S", default=d.jwt_lifetime, cast=int),
        )
