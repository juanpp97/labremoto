import threading

import numpy as np

from hardware.labrem_driver import STATE_BOOTED, STATE_HOMED

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


class RoutesLabRem(FakeLabRem):
    """FakeLabRem con la API que usan las rutas HTTP (inclinar, iniciar, gráficos)."""

    class AnguloInvalidoError(Exception):
        pass

    def __init__(self, state="Base lista"):
        super().__init__(state)
        self.calls = []
        self.outcome = "ok"  # "ok" | "fail" (devuelve 0) | "timeout" (lanza TimeOutError)
        self.gate = None  # Event: bloquea el comando "en vuelo" hasta que se setee
        self.entered = threading.Event()
        self.connected = False

    def conectar(self):  # equivale a LabRem.conectar() (broker MQTT)
        self.connected = True

    def _command(self, name):
        self.calls.append(name)
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.outcome == "timeout":
            raise self.TimeOutError("Tiempo de espera agotado")
        return 1 if self.outcome == "ok" else 0

    def enviarAnguloCin(self, angulo):
        ang = float(angulo)
        if ang > 15 or ang < 0:
            raise self.AnguloInvalidoError("Ángulo Inválido")
        return self._command(f"ang {ang}")

    def iniExp(self):
        return self._command("com1")

    def reinExp(self):
        return self._command("com4")

    def _png(self, tag):
        yield b"PNG-fake-"
        yield tag

    def GraficarDatos(self):
        return self._png(b"sensores")

    def GraficarDatos_accel(self):
        return self._png(b"accel")

    def GraficarDatos_vel(self):
        return self._png(b"vel")

    def GraficarDatos_esp(self):
        return self._png(b"esp")


class FakeReader:
    """Reader de cámara falso: frames negros infinitos (o `n_frames`)."""

    def __init__(self, n_frames=None):
        self.n_frames = n_frames
        self.closed = False
        self.yielded = 0

    def __iter__(self):
        while self.n_frames is None or self.yielded < self.n_frames:
            self.yielded += 1
            yield np.zeros((20, 20, 3), dtype=np.uint8)

    def close(self):
        self.closed = True


def inline_runner(fn):
    """reset_runner en línea: los resets corren en el mismo hilo (tests deterministas)."""
    fn()


class FakeHistoryStore:
    """Store de historial en memoria, con fallas y bloqueo simulables."""

    def __init__(self):
        self.rows = {}
        self.fail_upsert = False
        self.fail_orphans = False
        self.fail_recent = False
        self.gate = None  # Event: bloquea upsert hasta que se setee
        self.upserts = 0
        self.orphan_calls = []
        self._lock = threading.Lock()

    def upsert(self, record):
        if self.gate is not None:
            self.gate.wait(5)
        with self._lock:
            self.upserts += 1
            if self.fail_upsert:
                raise RuntimeError("DB caída")
            self.rows[record["lease_id"]] = dict(record)

    def close_orphans(self, before, ended_at):
        with self._lock:
            self.orphan_calls.append((before, ended_at))
            if self.fail_orphans:
                raise RuntimeError("DB caída")
        return 0

    def recent(self, limit):
        if self.fail_recent:
            raise RuntimeError("DB caída")
        rows = sorted(self.rows.values(), key=lambda r: r["acquired_at"], reverse=True)
        return [dict(r) for r in rows[:limit]]
