import dataclasses
import threading
import time

import pytest

from hardware.fake import FakeHardwareController
from lease.clock import FakeClock
from lease.errors import LeaseInvalid, ResourceBusy, ResourceFault
from lease.manager import LeaseManager
from lease.models import EndReason, LeaseState

DURATION = 900
HB_EVERY = 20
HB_TIMEOUT = 75
RESET_ESTIMATE = 10


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def hw():
    return FakeHardwareController()


@pytest.fixture
def mgr(clock, hw):
    return LeaseManager(
        hw,
        clock,
        lease_duration=DURATION,
        heartbeat_every=HB_EVERY,
        heartbeat_timeout=HB_TIMEOUT,
        watchdog_tick=0.005,
        retry_initial=0.01,
        retry_max=0.02,
        reset_estimate=RESET_ESTIMATE,
    )


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


# ------------------------------------------------------------------ acquire
def test_acquire_from_free_locks_and_issues_tokens(mgr):
    grant = mgr.acquire("alice")
    assert grant.lease_token and grant.stream_token
    assert grant.lease_token != grant.stream_token
    assert grant.epoch == 1
    assert grant.expires_in == DURATION
    assert grant.heartbeat_every == HB_EVERY
    assert grant.heartbeat_timeout == HB_TIMEOUT
    assert mgr.status().state is LeaseState.LOCKED


def test_acquire_other_user_is_busy_with_remaining_time(mgr, clock):
    mgr.acquire("alice")
    with pytest.raises(ResourceBusy) as exc:
        mgr.acquire("bob")
    assert exc.value.available_in == DURATION
    clock.advance(50)
    with pytest.raises(ResourceBusy) as exc:
        mgr.acquire("bob")
    assert exc.value.available_in == DURATION - 50


def test_concurrent_acquires_exactly_one_wins(mgr):
    n = 20
    barrier = threading.Barrier(n)
    results = []

    def worker(i):
        barrier.wait()
        try:
            results.append(("ok", mgr.acquire(f"user{i}")))
        except ResourceBusy:
            results.append(("busy", None))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert [r[0] for r in results].count("ok") == 1
    assert [r[0] for r in results].count("busy") == n - 1


def test_reacquire_same_user_is_idempotent_and_counts_as_heartbeat(mgr, clock):
    first = mgr.acquire("alice")
    clock.advance(70)
    again = mgr.acquire("alice")
    assert again.lease_token == first.lease_token
    assert again.stream_token == first.stream_token
    assert again.epoch == first.epoch
    assert again.expires_in == DURATION - 70
    clock.advance(70)  # 140s desde el inicio, pero solo 70 desde el re-acquire
    mgr.tick()
    assert mgr.status().state is LeaseState.LOCKED


def test_acquire_after_unticked_expiry_by_other_user_succeeds(mgr, clock, hw):
    old = mgr.acquire("alice")
    clock.advance(DURATION + 1)  # sin watchdog: lo detecta el chequeo lazy
    new = mgr.acquire("bob")
    assert new.epoch == old.epoch + 1
    assert hw.safe_state_calls == 1
    with pytest.raises(LeaseInvalid) as exc:
        mgr.validate(old.lease_token)
    assert exc.value.reason is EndReason.EXPIRED
    mgr.validate(new.lease_token)  # el lease nuevo no se afecta


# --------------------------------------------------------------- hard limit
def test_heartbeats_do_not_extend_the_hard_limit(mgr, clock):
    token = mgr.acquire("alice").lease_token
    elapsed = 0
    while elapsed < DURATION - HB_EVERY:
        clock.advance(HB_EVERY)
        elapsed += HB_EVERY
        assert mgr.renew(token) == DURATION - elapsed
    clock.advance(HB_EVERY)  # se alcanza el límite duro pese a heartbeats constantes
    with pytest.raises(LeaseInvalid) as exc:
        mgr.renew(token)
    assert exc.value.reason is EndReason.EXPIRED
    assert mgr.status().state is LeaseState.FREE


# ---------------------------------------------------------------- heartbeat
def test_no_heartbeat_watchdog_releases_after_timeout(mgr, clock, hw):
    mgr.acquire("alice")
    clock.advance(HB_TIMEOUT)  # justo en el borde: todavía vive
    mgr.tick()
    assert mgr.status().state is LeaseState.LOCKED
    clock.advance(1)
    mgr.tick()
    assert mgr.status().state is LeaseState.FREE
    assert hw.safe_state_calls == 1


def test_lazy_check_releases_without_watchdog(mgr, clock, hw):
    token = mgr.acquire("alice").lease_token
    clock.advance(HB_TIMEOUT + 1)
    with pytest.raises(LeaseInvalid) as exc:
        mgr.validate(token)
    assert exc.value.reason is EndReason.HEARTBEAT_TIMEOUT
    assert mgr.status().state is LeaseState.FREE
    assert hw.safe_state_calls == 1


def test_validate_counts_as_heartbeat(mgr, clock):
    token = mgr.acquire("alice").lease_token
    clock.advance(60)
    mgr.validate(token)
    clock.advance(60)
    mgr.tick()
    assert mgr.status().state is LeaseState.LOCKED


# ------------------------------------------------------------------ tokens
def test_release_with_wrong_token_is_invalid_and_keeps_lease(mgr):
    token = mgr.acquire("alice").lease_token
    with pytest.raises(LeaseInvalid) as exc:
        mgr.release("not-the-token")
    assert exc.value.reason is EndReason.UNKNOWN
    with pytest.raises(LeaseInvalid):
        mgr.release(None)
    assert mgr.validate(token)
    assert mgr.status().state is LeaseState.LOCKED


def test_old_lease_token_does_not_work_on_new_lease(mgr):
    old = mgr.acquire("alice")
    mgr.release(old.lease_token)
    new = mgr.acquire("bob")
    assert new.epoch == old.epoch + 1
    with pytest.raises(LeaseInvalid) as exc:
        mgr.release(old.lease_token)
    assert exc.value.reason is EndReason.RELEASED
    with pytest.raises(LeaseInvalid):
        mgr.validate(old.lease_token)
    assert mgr.validate(new.lease_token).epoch == new.epoch


def test_empty_token_is_invalid(mgr):
    mgr.acquire("alice")
    for bad in (None, ""):
        with pytest.raises(LeaseInvalid):
            mgr.validate(bad)


# -------------------------------------------------------------- safe_state
@pytest.mark.parametrize("cause", ["release", "expiry", "heartbeat", "force", "stop"])
def test_safe_state_called_exactly_once_per_session_end(mgr, clock, hw, cause):
    token = mgr.acquire("alice").lease_token
    if cause == "release":
        mgr.release(token)
    elif cause == "expiry":
        clock.advance(DURATION)
        mgr.tick()
    elif cause == "heartbeat":
        clock.advance(HB_TIMEOUT + 1)
        mgr.tick()
    elif cause == "force":
        assert mgr.force_release() is True
    else:
        mgr.stop()
    assert hw.safe_state_calls == 1
    assert mgr.status().state is LeaseState.FREE
    with pytest.raises(LeaseInvalid) as exc:
        mgr.validate(token)
    expected = {
        "release": EndReason.RELEASED,
        "expiry": EndReason.EXPIRED,
        "heartbeat": EndReason.HEARTBEAT_TIMEOUT,
        "force": EndReason.FORCED,
        "stop": EndReason.SERVER_SHUTDOWN,
    }[cause]
    assert exc.value.reason is expected


def test_safe_state_failure_goes_to_fault_then_manual_retry_frees(mgr, hw):
    mgr._stop_event.set()  # reintento automático desactivado en este test
    hw.failures_remaining = 1
    token = mgr.acquire("alice").lease_token
    mgr.release(token)
    assert mgr.status().state is LeaseState.FAULT
    assert mgr.status().available is False
    with pytest.raises(ResourceFault):
        mgr.acquire("bob")
    assert mgr.retry_safe_state() is LeaseState.FREE
    assert hw.safe_state_calls == 2
    assert mgr.acquire("bob")


def test_fault_recovers_automatically_with_backoff(mgr, hw):
    hw.failures_remaining = 2
    token = mgr.acquire("alice").lease_token
    mgr.release(token)
    assert wait_until(lambda: mgr.status().state is LeaseState.FREE)
    assert hw.safe_state_calls == 3


def test_force_release_in_fault_retries_safe_state(mgr, hw):
    mgr._stop_event.set()  # reintento automático desactivado
    hw.failures_remaining = 1
    mgr.release(mgr.acquire("alice").lease_token)
    assert mgr.status().state is LeaseState.FAULT
    assert mgr.force_release() is True
    assert mgr.status().state is LeaseState.FREE


def test_force_release_when_free_is_noop(mgr, hw):
    assert mgr.force_release() is False
    assert hw.safe_state_calls == 0


def test_safe_state_runs_outside_the_manager_lock(mgr, hw):
    """Mientras el hardware se resetea, status/acquire siguen respondiendo."""
    hw.safe_state_gate = threading.Event()
    token = mgr.acquire("alice").lease_token
    releaser = threading.Thread(target=mgr.release, args=(token,))
    releaser.start()
    assert hw.safe_state_entered.wait(2)

    observed = {}

    def probe():
        observed["status"] = mgr.status()
        try:
            mgr.acquire("bob")
        except ResourceBusy as e:
            observed["busy"] = e.available_in

    prober = threading.Thread(target=probe)
    prober.start()
    prober.join(2)
    assert not prober.is_alive(), "el lock del manager quedó tomado durante safe_state"
    assert observed["status"].state is LeaseState.RESETTING
    assert observed["busy"] == RESET_ESTIMATE

    hw.safe_state_gate.set()
    releaser.join(2)
    assert mgr.status().state is LeaseState.FREE


def test_token_is_invalidated_before_hardware_is_touched(mgr, hw):
    hw.safe_state_gate = threading.Event()
    token = mgr.acquire("alice").lease_token
    releaser = threading.Thread(target=mgr.release, args=(token,))
    releaser.start()
    assert hw.safe_state_entered.wait(2)
    with pytest.raises(LeaseInvalid) as exc:
        mgr.validate(token)
    assert exc.value.reason is EndReason.RELEASED
    hw.safe_state_gate.set()
    releaser.join(2)


# ---------------------------------------------------------------- watchdog
def test_watchdog_survives_internal_exception(mgr):
    calls = []

    def flaky_tick():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    mgr.tick = flaky_tick
    mgr.start()
    try:
        assert wait_until(lambda: len(calls) >= 3)
    finally:
        mgr.stop()


def test_watchdog_thread_releases_lease_end_to_end(mgr, clock):
    mgr.acquire("alice")
    clock.advance(HB_TIMEOUT + 1)
    mgr.start()
    try:
        assert wait_until(lambda: mgr.status().state is LeaseState.FREE)
    finally:
        mgr.stop()


def test_stop_releases_and_leaves_hardware_safe(mgr, hw):
    token = mgr.acquire("alice").lease_token
    mgr.start()
    mgr.stop()
    assert mgr.status().state is LeaseState.FREE
    assert hw.safe_state_calls == 1
    with pytest.raises(LeaseInvalid):
        mgr.validate(token)


def test_stop_when_free_still_runs_safe_state(mgr, hw):
    mgr.stop()
    assert hw.safe_state_calls == 1


# --------------------------------------------------------- fencing / status
def test_is_current_follows_lease_lifecycle(mgr, clock):
    grant = mgr.acquire("alice")
    assert mgr.is_current(grant.epoch)
    assert not mgr.is_current(grant.epoch + 1)
    clock.advance(DURATION)  # vencido por tiempo aunque nadie lo haya procesado
    assert not mgr.is_current(grant.epoch)

    grant2 = mgr.acquire("alice")
    assert mgr.is_current(grant2.epoch)
    mgr.release(grant2.lease_token)
    assert not mgr.is_current(grant2.epoch)


def test_validate_stream_does_not_count_as_heartbeat(mgr, clock):
    grant = mgr.acquire("alice")
    clock.advance(50)
    assert mgr.validate_stream(grant.stream_token) == grant.epoch
    clock.advance(30)  # 80s sin heartbeat real
    with pytest.raises(LeaseInvalid):
        mgr.validate_stream(grant.stream_token)


def test_stream_token_invalid_after_release_and_lease_token_is_not_a_stream_token(mgr):
    grant = mgr.acquire("alice")
    with pytest.raises(LeaseInvalid):
        mgr.validate_stream(grant.lease_token)
    mgr.release(grant.lease_token)
    with pytest.raises(LeaseInvalid):
        mgr.validate_stream(grant.stream_token)


def test_status_never_exposes_user_id(mgr):
    mgr.acquire("alice")
    snapshot = mgr.status()
    assert {f.name for f in dataclasses.fields(snapshot)} == {
        "state", "available", "available_in_seconds",
    }
    assert "alice" not in repr(snapshot)


def test_status_free_and_locked(mgr, clock):
    assert mgr.status().available is True
    mgr.acquire("alice")
    clock.advance(100)
    snapshot = mgr.status()
    assert snapshot.available is False
    assert snapshot.available_in_seconds == DURATION - 100


# ------------------------------------------------------------------- config
def test_constructor_rejects_inconsistent_timings(clock, hw):
    with pytest.raises(ValueError):
        LeaseManager(hw, clock, heartbeat_every=80, heartbeat_timeout=75)
    with pytest.raises(ValueError):
        LeaseManager(hw, clock, heartbeat_timeout=1000, lease_duration=900)
