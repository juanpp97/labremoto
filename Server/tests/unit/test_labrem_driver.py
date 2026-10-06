import pytest

from hardware.errors import HardwareError
from hardware.labrem_driver import STATE_HOMED, LabRemDriver
from tests.fakes import FakeLabRem


class Time:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


def driver_for(lr, **kw):
    t = Time()
    return LabRemDriver(lr, sleep=t.sleep, monotonic=t.monotonic, **kw)


def test_already_homed_sends_nothing():
    lr = FakeLabRem(STATE_HOMED)
    driver_for(lr).safe_state()
    assert lr.sent == [] and lr.hard_resets == 0


def test_ready_base_is_homed_with_com4_and_target():
    lr = FakeLabRem("Base lista")
    driver_for(lr).safe_state()
    assert lr.sent == [("com4", STATE_HOMED)]
    assert lr.hard_resets == 0
    assert lr.estado_base == STATE_HOMED


def test_waits_for_base_to_become_ready_mid_command():
    lr = FakeLabRem("Base lista")
    lr.busy_polls = 5
    driver_for(lr).safe_state()
    assert lr.sent == [("com4", STATE_HOMED)]
    assert lr.hard_resets == 0


def test_com4_timeout_falls_back_to_hard_reset_then_homes():
    lr = FakeLabRem("Base lista")
    lr.com4_script = ["timeout", "ok"]
    driver_for(lr).safe_state()
    assert lr.hard_resets == 1
    assert [m for m, _ in lr.sent] == ["com4", "com4"]
    assert lr.estado_base == STATE_HOMED


def test_base_never_ready_falls_back_to_hard_reset():
    lr = FakeLabRem("Iniciando Exp...")
    driver_for(lr, ready_wait=5).safe_state()  # tras el reset queda en BOOTED (lista)
    assert lr.hard_resets == 1
    assert lr.estado_base == STATE_HOMED


def test_micros_do_not_come_back_after_reset_raises():
    lr = FakeLabRem("Base lista")
    lr.com4_script = ["timeout"]
    lr.boot_after_reset = False
    with pytest.raises(HardwareError):
        driver_for(lr, reset_wait=3).safe_state()
    assert lr.hard_resets == 1


def test_homing_still_fails_after_reset_raises():
    lr = FakeLabRem("Base lista")
    lr.com4_script = ["timeout", "timeout"]
    with pytest.raises(HardwareError):
        driver_for(lr).safe_state()
    assert lr.hard_resets == 1


def test_safe_state_is_idempotent():
    lr = FakeLabRem("Base lista")
    d = driver_for(lr)
    d.safe_state()
    d.safe_state()
    assert [m for m, _ in lr.sent] == ["com4"]  # la segunda vez ya estaba en 0
