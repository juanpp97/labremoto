import threading
import time

import pytest

from hardware.errors import HardwareError
from hardware.fake import FakeHardwareController
from lease.clock import FakeClock
from lease.errors import LeaseRevoked
from lease.manager import LeaseManager
from lease.models import LeaseContext, LeaseState
from tests.fakes import inline_runner

DURATION = 900
HB_TIMEOUT = 75


def make(safe_state_lock_timeout=60.0):
    clock = FakeClock()
    hw = FakeHardwareController(safe_state_lock_timeout=safe_state_lock_timeout)
    mgr = LeaseManager(
        hw, clock, lease_duration=DURATION, heartbeat_every=20,
        heartbeat_timeout=HB_TIMEOUT, retry_initial=0.01, retry_max=0.02,
        reset_runner=inline_runner,
    )
    hw.attach_lease_checker(mgr.is_current)
    return clock, hw, mgr


def ctx_of(mgr, user="alice"):
    grant = mgr.acquire(user)
    return grant, LeaseContext(grant.lease_token, grant.epoch)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_run_executes_op_with_current_lease():
    _, hw, mgr = make()
    _, ctx = ctx_of(mgr)
    assert hw.run(ctx, lambda: 42) == 42


def test_run_refuses_without_lease_checker():
    hw = FakeHardwareController()
    with pytest.raises(RuntimeError):
        hw.run(LeaseContext("t", 1), lambda: None)


def test_run_with_stale_epoch_raises_and_does_not_execute():
    _, hw, mgr = make()
    grant, ctx = ctx_of(mgr)
    executed = []
    with pytest.raises(LeaseRevoked):
        hw.run(LeaseContext(ctx.token, grant.epoch + 1), lambda: executed.append(1))
    assert executed == []


def test_run_after_release_is_revoked():
    _, hw, mgr = make()
    grant, ctx = ctx_of(mgr)
    mgr.release(grant.lease_token)
    with pytest.raises(LeaseRevoked):
        hw.run(ctx, lambda: pytest.fail("no debió ejecutarse"))


def test_old_epoch_cannot_operate_on_new_lease():
    _, hw, mgr = make()
    grant, old_ctx = ctx_of(mgr, "alice")
    mgr.release(grant.lease_token)
    ctx_of(mgr, "bob")
    with pytest.raises(LeaseRevoked):
        hw.run(old_ctx, lambda: pytest.fail("no debió ejecutarse"))


def test_run_is_revoked_when_lease_expired_by_time_even_if_not_processed():
    clock, hw, mgr = make()
    _, ctx = ctx_of(mgr)
    clock.advance(DURATION)  # el watchdog todavía no lo procesó
    with pytest.raises(LeaseRevoked):
        hw.run(ctx, lambda: pytest.fail("no debió ejecutarse"))


def test_run_is_revoked_while_in_fault():
    _, hw, mgr = make()
    mgr._stop_event.set()  # sin reintento automático
    hw.failures_remaining = 1
    grant, ctx = ctx_of(mgr)
    mgr.release(grant.lease_token)
    assert mgr.status().state is LeaseState.FAULT
    with pytest.raises(LeaseRevoked):
        hw.run(ctx, lambda: pytest.fail("no debió ejecutarse"))


def test_race_inflight_command_vs_expiry():
    """§7: comando en vuelo + vencimiento. safe_state espera al comando en vuelo y
    el comando encolado detrás nunca llega a ejecutarse."""
    clock, hw, mgr = make()
    grant, ctx = ctx_of(mgr)
    events = []
    started = threading.Event()
    finish = threading.Event()

    def long_op():
        events.append("op1:start")
        started.set()
        finish.wait(5)
        events.append("op1:end")

    results = {}

    def run_op1():
        hw.run(ctx, long_op)

    def run_op2():
        try:
            hw.run(ctx, lambda: events.append("op2:EXECUTED"))
        except LeaseRevoked:
            results["op2"] = "revoked"

    t1 = threading.Thread(target=run_op1)
    t1.start()
    assert started.wait(2)

    # El lease vence mientras op1 está en vuelo.
    clock.advance(DURATION)
    real_safe_state = hw.driver.safe_state
    hw.driver.safe_state = lambda: (events.append("safe_state"), real_safe_state())[1]
    watchdog = threading.Thread(target=mgr.tick)
    watchdog.start()
    assert wait_until(lambda: mgr.status().state is LeaseState.RESETTING)

    t2 = threading.Thread(target=run_op2)
    t2.start()
    t2.join(2)
    assert results["op2"] == "revoked"  # fast-fail: ni siquiera se encola

    time.sleep(0.05)
    assert "safe_state" not in events  # safe_state sigue esperando a op1

    finish.set()
    t1.join(2)
    watchdog.join(2)
    assert events == ["op1:start", "op1:end", "safe_state"]
    assert mgr.status().state is LeaseState.FREE


def test_queued_command_behind_inflight_one_fails_after_it_finishes():
    """Un comando ya esperando el io_lock cuando se revoca el lease no se ejecuta."""
    _, hw, mgr = make()
    grant, ctx = ctx_of(mgr)
    events = []
    started = threading.Event()
    finish = threading.Event()
    results = {}

    def long_op():
        started.set()
        finish.wait(5)

    t1 = threading.Thread(target=lambda: hw.run(ctx, long_op))
    t1.start()
    assert started.wait(2)

    def queued():
        try:
            hw.run(ctx, lambda: events.append("queued:EXECUTED"))
        except LeaseRevoked:
            results["queued"] = "revoked"

    t2 = threading.Thread(target=queued)
    t2.start()
    time.sleep(0.05)  # t2 ya pasó el fast-fail y está esperando el lock
    releaser = threading.Thread(target=mgr.release, args=(grant.lease_token,))
    releaser.start()
    time.sleep(0.05)
    finish.set()
    for t in (t1, t2, releaser):
        t.join(2)
    assert results["queued"] == "revoked"
    assert events == []
    assert mgr.status().state is LeaseState.FREE


def test_safe_state_lock_timeout_leads_to_fault_then_recovers():
    _, hw, mgr = make(safe_state_lock_timeout=0.05)
    grant, ctx = ctx_of(mgr)
    started = threading.Event()
    finish = threading.Event()

    def hung_op():
        started.set()
        finish.wait(5)

    t1 = threading.Thread(target=lambda: hw.run(ctx, hung_op))
    t1.start()
    assert started.wait(2)

    mgr.release(grant.lease_token)  # safe_state no consigue el io_lock
    assert wait_until(lambda: mgr.status().state is LeaseState.FAULT)
    assert hw.safe_state_calls == 0

    finish.set()  # el comando termina; el reintento automático ya puede entrar
    t1.join(2)
    assert wait_until(lambda: mgr.status().state is LeaseState.FREE)
    assert hw.safe_state_calls == 1


def test_safe_state_lock_timeout_raises_hardware_error_directly():
    hw = FakeHardwareController(safe_state_lock_timeout=0.05)
    hw.attach_lease_checker(lambda epoch: True)
    started = threading.Event()
    finish = threading.Event()
    t = threading.Thread(
        target=lambda: hw.run(LeaseContext("t", 1), lambda: (started.set(), finish.wait(5)))
    )
    t.start()
    assert started.wait(2)
    with pytest.raises(HardwareError):
        hw.safe_state()
    finish.set()
    t.join(2)


def test_no_command_runs_during_safe_state():
    _, hw, mgr = make()
    hw.safe_state_gate = threading.Event()
    grant, ctx = ctx_of(mgr)
    releaser = threading.Thread(target=mgr.release, args=(grant.lease_token,))
    releaser.start()
    assert hw.safe_state_entered.wait(2)
    with pytest.raises(LeaseRevoked):
        hw.run(ctx, lambda: pytest.fail("no debió ejecutarse durante safe_state"))
    hw.safe_state_gate.set()
    releaser.join(2)
