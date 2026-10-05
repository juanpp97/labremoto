import threading
from typing import Callable, Optional, Protocol, TypeVar

from lease.errors import LeaseRevoked
from lease.models import LeaseContext

from .errors import HardwareError

T = TypeVar("T")


class HardwareDriver(Protocol):
    def safe_state(self) -> None:
        """Deja el hardware en estado seguro. Idempotente."""
        ...


class HardwareController:
    """Único punto de acceso al hardware.

    `_io_lock` serializa TODO acceso físico, incluido safe_state(). Cada operación
    re-verifica el epoch del lease adentro del lock (fencing): si el lease terminó
    mientras la operación esperaba, no se ejecuta. Así ningún comando puede correr
    después de que empezó el safe_state de la sesión.
    """

    def __init__(self, driver: HardwareDriver, safe_state_lock_timeout: float = 60.0):
        self._driver = driver
        self._safe_state_lock_timeout = safe_state_lock_timeout
        self._io_lock = threading.Lock()
        self._is_current: Optional[Callable[[int], bool]] = None

    def attach_lease_checker(self, is_current: Callable[[int], bool]) -> None:
        """Conecta el chequeo de epoch (LeaseManager.is_current)."""
        self._is_current = is_current

    def run(self, ctx: LeaseContext, op: Callable[[], T]) -> T:
        if self._is_current is None:
            raise RuntimeError("HardwareController sin lease checker: se niega a operar")
        # Fast-fail: no hace falta encolarse detrás de un safe_state en curso.
        if not self._is_current(ctx.epoch):
            raise LeaseRevoked("lease terminado")
        with self._io_lock:
            if not self._is_current(ctx.epoch):
                raise LeaseRevoked("lease terminado mientras esperaba el hardware")
            return op()

    def safe_state(self) -> None:
        # Espera a que termine el comando en vuelo. Los comandos del driver tienen
        # timeout propio, pero si algo se cuelga no esperamos indefinidamente:
        # falla (-> FAULT, visible) en lugar de dejar el recurso en un limbo.
        if not self._io_lock.acquire(timeout=self._safe_state_lock_timeout):
            raise HardwareError("safe_state: el hardware sigue ocupado por un comando en vuelo")
        try:
            self._driver.safe_state()
        finally:
            self._io_lock.release()
