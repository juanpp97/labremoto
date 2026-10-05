import pytest

from hardware.errors import HardwareError
from hardware.labrem_driver import STATE_BOOTED, STATE_HOMED, LabRemDriver

READY = ("Base lista", STATE_HOMED, STATE_BOOTED)


class FakeLabRem:
    """Simula el módulo LabRem: estado de la base + comandos MQTT."""

    topic_comandos_cin = "/test/com"

    class TimeOutError(Exception):
        pass

    def __init__(self, state="Base lista"):
        self.estado_base = state
        self.sent = []
        self.hard_resets = 0
        # com4 -> lista de resultados: "ok" | "timeout"
        self.com4_script = []
        self.busy_polls = 0  # cuántas consultas devuelven "no listo" antes de estarlo
        self.boot_after_reset = True

    def consultarEstado(self, target=0):
        if self.busy_polls > 0:
            self.busy_polls -= 1
            return False
        if target == 0:
            return self.estado_base in READY
        return self.estado_base == target

    def enviarComandoBM(self, topic, message, timeout, target=0):
        self.sent.append((message, target))
        outcome = self.com4_script.pop(0) if self.com4_script else "ok"
        if outcome == "timeout":
            raise self.TimeOutError("Tiempo de espera agotado")
        self.estado_base = target if target else self.estado_base
        return 1

    def hardReset(self):
        self.hard_resets += 1
        self.estado_base = STATE_BOOTED if self.boot_after_reset else "Reiniciando"


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
