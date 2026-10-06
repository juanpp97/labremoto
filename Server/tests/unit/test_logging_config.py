import io
import json
import logging

import pytest

from hardware.fake import FakeHardwareController
from lease.clock import FakeClock
from lease.logging_config import JsonFormatter, configure_logging
from lease.manager import LeaseManager
from tests.fakes import inline_runner


def make_record(**extra):
    record = logging.LogRecord("lease", logging.INFO, __file__, 1, "hola %s", ("mundo",), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_valid_json_line_with_extras():
    line = JsonFormatter().format(make_record(event="x", epoch=3, user_id=None))
    assert "\n" not in line
    data = json.loads(line)
    assert data["message"] == "hola mundo"
    assert data["level"] == "INFO" and data["logger"] == "lease"
    assert data["event"] == "x" and data["epoch"] == 3 and data["user_id"] is None
    assert data["ts"].endswith("+00:00")
    assert "msg" not in data and "args" not in data  # internos de LogRecord no se filtran


def test_json_formatter_includes_exception_text():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord("l", logging.ERROR, __file__, 1, "falló", (), sys.exc_info())
    data = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in data["exc"]


def test_json_formatter_serializes_non_json_values():
    data = json.loads(JsonFormatter().format(make_record(obj=object())))
    assert isinstance(data["obj"], str)


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    # otro test (el smoke de app.py) puede haber instalado ya el handler propio
    root.handlers[:] = [h for h in saved_handlers if not getattr(h, "_labrem", False)]
    yield root
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_configure_logging_is_idempotent_and_switches_format(clean_root):
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream)
    configure_logging("DEBUG", "json", stream=stream)
    ours = [h for h in clean_root.handlers if getattr(h, "_labrem", False)]
    assert len(ours) == 1 and clean_root.level == logging.DEBUG

    logging.getLogger("t").info("uno", extra={"k": 1})
    assert json.loads(stream.getvalue().splitlines()[-1])["k"] == 1

    configure_logging("INFO", "text", stream=stream)
    assert isinstance(ours[0].formatter, logging.Formatter)
    assert not isinstance(ours[0].formatter, JsonFormatter)
    assert len([h for h in clean_root.handlers if getattr(h, "_labrem", False)]) == 1


def test_lease_transitions_are_logged_with_structured_fields(caplog):
    mgr = LeaseManager(
        FakeHardwareController(), FakeClock(), reset_runner=inline_runner,
    )
    with caplog.at_level(logging.INFO, logger="lease"):
        grant = mgr.acquire("alice")
        mgr.release(grant.lease_token)
    transitions = [r for r in caplog.records if getattr(r, "event", None) == "lease_transition"]
    assert [(r.from_state, r.to_state, r.reason) for r in transitions] == [
        ("FREE", "LOCKED", "acquire"),
        ("LOCKED", "RESETTING", "released"),
        ("RESETTING", "FREE", "safe_state_ok"),
    ]
    assert transitions[0].user_id == "alice" and transitions[0].epoch == 1
    # el JSON final contiene los campos pedidos por el plan
    data = json.loads(JsonFormatter().format(transitions[0]))
    assert {"from_state", "to_state", "reason", "user_id", "epoch"} <= set(data)
