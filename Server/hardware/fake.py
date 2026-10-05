import threading
from typing import Optional

from .controller import HardwareController
from .errors import HardwareError


class FakeDriver:
    """Driver simulado: cuenta llamadas a safe_state y permite simular fallos/bloqueos."""

    def __init__(self):
        self.safe_state_calls = 0
        self.failures_remaining = 0
        # Si se asigna un Event, safe_state se bloquea hasta que se setee.
        self.safe_state_gate: Optional[threading.Event] = None
        self.safe_state_entered = threading.Event()
        self._lock = threading.Lock()

    def safe_state(self) -> None:
        with self._lock:
            self.safe_state_calls += 1
            fail = self.failures_remaining > 0
            if fail:
                self.failures_remaining -= 1
        self.safe_state_entered.set()
        if self.safe_state_gate is not None:
            self.safe_state_gate.wait(5)
        if fail:
            raise HardwareError("safe_state simulado: falla")


def _delegate(name):
    return property(
        lambda self: getattr(self.driver, name),
        lambda self, value: setattr(self.driver, name, value),
    )


class FakeHardwareController(HardwareController):
    """Controller real (io_lock + fencing) sobre un FakeDriver. Para tests y modo mock."""

    safe_state_calls = _delegate("safe_state_calls")
    failures_remaining = _delegate("failures_remaining")
    safe_state_gate = _delegate("safe_state_gate")
    safe_state_entered = _delegate("safe_state_entered")

    def __init__(self, **kwargs):
        self.driver = FakeDriver()
        super().__init__(self.driver, **kwargs)
