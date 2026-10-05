import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Segundos monotónicos. Solo sirve para medir intervalos."""
        ...


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


class FakeClock:
    """Reloj manual para tests: el tiempo solo avanza con advance()."""

    def __init__(self, start: float = 1000.0):
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
