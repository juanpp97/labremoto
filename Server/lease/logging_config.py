import json
import logging
import sys
from datetime import datetime, timezone

# Atributos propios de LogRecord: todo lo demás en el record son campos `extra`.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro, con los campos `extra` como claves propias."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO", fmt: str = "json", stream=None) -> None:
    """Configura el logger raíz hacia stdout. Idempotente (no duplica handlers)."""
    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, "_labrem", False)), None)
    if handler is None:
        handler = logging.StreamHandler(stream or sys.stdout)
        handler._labrem = True
        root.addHandler(handler)
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(_TEXT_FORMAT))
    root.setLevel(level.upper())
