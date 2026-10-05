import logging
import time
from typing import Callable

from .errors import HardwareError

logger = logging.getLogger("hardware")

STATE_HOMED = "Exp Reiniciado"
STATE_BOOTED = "ESPERANDO COMANDO   "  # los espacios finales vienen del firmware


class LabRemDriver:
    """Driver real: opera la base por MQTT a través del módulo LabRem.

    `lr` es el módulo LabRem (inyectado para poder testear sin broker).
    safe_state():
      1. esperar a que la base esté lista (puede estar a mitad de un comando),
      2. com4 (rampa a 0) verificando el estado "Exp Reiniciado",
      3. si falla: com6 (reset de micros), esperar que arranquen y repetir 2,
      4. si nada funciona: HardwareError (el manager pasa a FAULT).
    """

    def __init__(
        self,
        lr,
        ready_wait: float = 30.0,
        command_timeout: float = 10.0,
        reset_wait: float = 20.0,
        poll: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self._lr = lr
        self._ready_wait = ready_wait
        self._command_timeout = command_timeout
        self._reset_wait = reset_wait
        self._poll = poll
        self._sleep = sleep
        self._monotonic = monotonic

    def safe_state(self) -> None:
        if self._try_home():
            return
        logger.warning("safe_state: com4 no alcanzó; se hace reset de micros (com6)")
        self._lr.hardReset()
        if not self._wait_for(lambda: self._lr.consultarEstado(STATE_BOOTED), self._reset_wait):
            raise HardwareError("safe_state: los micros no volvieron tras el reset")
        if not self._try_home():
            raise HardwareError("safe_state: no se pudo llevar la base a 0 tras el reset")

    def _try_home(self) -> bool:
        lr = self._lr
        if not self._wait_for(lr.consultarEstado, self._ready_wait):
            logger.warning("safe_state: la base no quedó lista en %ss", self._ready_wait)
            return False
        if lr.estado_base == STATE_HOMED:
            return True  # ya está en 0; idempotente
        try:
            res = lr.enviarComandoBM(
                lr.topic_comandos_cin, "com4", self._command_timeout, target=STATE_HOMED
            )
        except lr.TimeOutError:
            logger.warning("safe_state: timeout esperando '%s'", STATE_HOMED)
            return False
        return bool(res)

    def _wait_for(self, predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = self._monotonic() + timeout
        while True:
            if predicate():
                return True
            if self._monotonic() >= deadline:
                return False
            self._sleep(self._poll)
