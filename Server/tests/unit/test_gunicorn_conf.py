import runpy
from pathlib import Path

CONF = Path(__file__).resolve().parents[2] / "gunicorn.conf.py"
ENV_VARS = ("GUNICORN_BIND", "GUNICORN_THREADS", "GUNICORN_ACCESSLOG", "GUNICORN_WORKERS")


def load(monkeypatch, **env):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(CONF))


def test_defaults(monkeypatch):
    conf = load(monkeypatch)
    assert conf["workers"] == 1
    assert conf["worker_class"] == "gthread"
    assert conf["threads"] == 6
    assert conf["bind"] == "0.0.0.0:80"
    assert conf["accesslog"] is None
    assert conf["graceful_timeout"] >= 120


def test_workers_cannot_be_overridden_from_the_environment(monkeypatch):
    assert load(monkeypatch, GUNICORN_WORKERS="4")["workers"] == 1


def test_threads_bind_and_accesslog_are_configurable(monkeypatch):
    conf = load(
        monkeypatch, GUNICORN_THREADS="8", GUNICORN_BIND="127.0.0.1:8000", GUNICORN_ACCESSLOG="1"
    )
    assert conf["threads"] == 8
    assert conf["bind"] == "127.0.0.1:8000"
    assert conf["accesslog"] == "-"
    assert "x-forwarded-for" in conf["access_log_format"]
