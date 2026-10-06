"""Reset asíncrono (runner por defecto): ningún request espera al hardware."""
import threading
import time

import pytest

from hardware.fake import FakeHardwareController
from lease.clock import FakeClock
from lease.errors import LeaseInvalid, ResourceBusy
from lease.manager import LeaseManager
from lease.models import EndReason, LeaseState

DURATION = 900
HB_TIMEOUT = 75


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def hw():
    hardware = FakeHardwareController()
    hardware.safe_state_gate = threading.Event()  # el reset queda colgado hasta setearlo
    return hardware


@pytest.fixture
def mgr(clock, hw):
    manager = LeaseManager(
        hw, clock, lease_duration=DURATION, heartbeat_every=20,
        heartbeat_timeout=HB_TIMEOUT, watchdog_tick=60, retry_initial=0.01, retry_max=0.02,
        reset_estimate=10,
    )  # sin reset_runner: hilo por defecto
    yield manager
    hw.safe_state_gate.set()
    manager.stop()


def returns_promptly(fn, timeout=1.0):
    """Ejecuta fn en un hilo y verifica que vuelva sin esperar al hardware."""
    result = {}

    def target():
        try:
            result["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=target)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "la llamada quedó esperando a safe_state"
    return result


def test_release_returns_while_safe_state_is_still_running(mgr, hw):
    token = mgr.acquire("alice").lease_token
    result = returns_promptly(lambda: mgr.release(token))
    assert "error" not in result
    assert hw.safe_state_entered.wait(2)
    assert mgr.status().state is LeaseState.RESETTING
    with pytest.raises(LeaseInvalid) as exc:  # el token ya está revocado
        mgr.validate(token)
    assert exc.value.reason is EndReason.RELEASED

    hw.safe_state_gate.set()
    assert wait_until(lambda: mgr.status().state is LeaseState.FREE)
    assert hw.safe_state_calls == 1


def test_lazy_expiry_in_validate_does_not_wait_for_hardware(mgr, hw, clock):
    token = mgr.acquire("alice").lease_token
    clock.advance(HB_TIMEOUT + 1)
    result = returns_promptly(lambda: mgr.validate(token))
    assert isinstance(result["error"], LeaseInvalid)
    assert result["error"].reason is EndReason.HEARTBEAT_TIMEOUT


def test_lazy_expiry_in_renew_does_not_wait_for_hardware(mgr, hw, clock):
    token = mgr.acquire("alice").lease_token
    clock.advance(DURATION)
    result = returns_promptly(lambda: mgr.renew(token))
    assert result["error"].reason is EndReason.EXPIRED


def test_acquire_right_after_expiry_gets_busy_then_succeeds_when_reset_ends(mgr, hw, clock):
    mgr.acquire("alice")
    clock.advance(DURATION + 1)
    result = returns_promptly(lambda: mgr.acquire("bob"))
    assert isinstance(result["error"], ResourceBusy)
    assert result["error"].available_in == 10

    hw.safe_state_gate.set()
    assert wait_until(lambda: mgr.status().state is LeaseState.FREE)
    assert mgr.acquire("bob")


def test_force_release_locked_does_not_block(mgr, hw):
    mgr.acquire("alice")
    result = returns_promptly(mgr.force_release)
    assert result["value"] is True
    assert mgr.status().state is LeaseState.RESETTING


def test_force_release_in_fault_does_not_block_and_recovers(mgr, hw):
    mgr._stop_event.set()  # sin reintento automático: lo dispara el admin
    hw.safe_state_gate.set()
    hw.failures_remaining = 1
    mgr.release(mgr.acquire("alice").lease_token)
    assert wait_until(lambda: mgr.status().state is LeaseState.FAULT)

    hw.safe_state_gate = threading.Event()
    hw.safe_state_entered.clear()
    result = returns_promptly(mgr.force_release)
    assert result["value"] is True
    assert hw.safe_state_entered.wait(2)
    assert mgr.status().state is LeaseState.RESETTING
    hw.safe_state_gate.set()
    assert wait_until(lambda: mgr.status().state is LeaseState.FREE)


def test_tick_does_not_block_the_watchdog(mgr, hw, clock):
    mgr.acquire("alice")
    clock.advance(HB_TIMEOUT + 1)
    returns_promptly(mgr.tick)
    assert mgr.status().state is LeaseState.RESETTING


def test_stop_waits_for_an_inflight_reset_and_is_idempotent(mgr, hw):
    token = mgr.acquire("alice").lease_token
    mgr.release(token)
    assert hw.safe_state_entered.wait(2)

    stopper = threading.Thread(target=mgr.stop)
    stopper.start()
    time.sleep(0.05)
    assert stopper.is_alive(), "stop() no esperó al reset en vuelo"
    hw.safe_state_gate.set()
    stopper.join(5)
    assert not stopper.is_alive()

    calls_after_first_stop = hw.safe_state_calls
    mgr.stop()  # segunda llamada: no hace nada
    assert hw.safe_state_calls == calls_after_first_stop


def test_stop_with_active_lease_resets_synchronously(mgr, hw):
    hw.safe_state_gate.set()
    token = mgr.acquire("alice").lease_token
    mgr.stop()
    assert mgr.status().state is LeaseState.FREE
    with pytest.raises(LeaseInvalid) as exc:
        mgr.validate(token)
    assert exc.value.reason is EndReason.SERVER_SHUTDOWN
