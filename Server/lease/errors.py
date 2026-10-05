from .models import EndReason


class LeaseError(Exception):
    pass


class LeaseInvalid(LeaseError):
    """Token ausente, desconocido, o de un lease que ya terminó."""

    def __init__(self, reason: EndReason = EndReason.UNKNOWN):
        super().__init__(reason.value)
        self.reason = reason


class LeaseRevoked(LeaseError):
    """El lease terminó mientras un comando esperaba para ejecutarse (fencing)."""


class ResourceBusy(LeaseError):
    def __init__(self, available_in: int):
        super().__init__(f"resource busy, available in ~{available_in}s")
        self.available_in = available_in


class ResourceFault(LeaseError):
    """safe_state falló: el recurso no se entrega hasta recuperarlo."""
