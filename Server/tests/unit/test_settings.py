from lease.settings import LeaseSettings

VARS = [
    "LEASE_DURATION_S", "HEARTBEAT_EVERY_S", "HEARTBEAT_TIMEOUT_S",
    "WATCHDOG_TICK_S", "SAFE_STATE_RETRY_INITIAL_S", "SAFE_STATE_RETRY_MAX_S",
    "JWT_LIFETIME_S",
]


def test_defaults_match_the_plan(monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    s = LeaseSettings.from_env()
    assert (s.lease_duration, s.heartbeat_every, s.heartbeat_timeout) == (900, 20, 75)
    assert (s.watchdog_tick, s.safe_state_retry_max) == (5, 30)
    assert s.jwt_lifetime == 3600


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("LEASE_DURATION_S", "600")
    monkeypatch.setenv("HEARTBEAT_EVERY_S", "10")
    monkeypatch.setenv("HEARTBEAT_TIMEOUT_S", "40")
    monkeypatch.setenv("WATCHDOG_TICK_S", "2.5")
    monkeypatch.setenv("JWT_LIFETIME_S", "7200")
    s = LeaseSettings.from_env()
    assert (s.lease_duration, s.heartbeat_every, s.heartbeat_timeout) == (600, 10, 40)
    assert s.watchdog_tick == 2.5
    assert s.jwt_lifetime == 7200
