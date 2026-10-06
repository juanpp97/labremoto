import os
from typing import Optional

try:  # POSIX (Raspberry Pi)
    import fcntl
except ImportError:  # Windows (desarrollo)
    fcntl = None
    import msvcrt


class ProcessLockError(RuntimeError):
    """Ya hay otro proceso controlando el laboratorio."""


class ProcessLock:
    """Lock exclusivo de archivo, no bloqueante, atado a la vida del proceso.

    El estado del lease vive en memoria, así que solo puede haber UN proceso/worker.
    Si alguien levanta un segundo (p. ej. `gunicorn --workers 2`), falla al arrancar en
    lugar de repartir el recurso en silencio. El SO libera el lock si el proceso muere.
    """

    def __init__(self, path: str):
        self._path = path
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            os.close(fd)
            raise ProcessLockError(
                f"otro proceso ya controla el laboratorio (lock: {self._path}); "
                "el lease requiere un único proceso/worker"
            ) from None
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


def acquire_process_lock(path: Optional[str]) -> Optional[ProcessLock]:
    """Toma el lock en `path`; con ruta vacía o None, el guard queda desactivado."""
    if not path:
        return None
    lock = ProcessLock(path)
    lock.acquire()
    return lock
