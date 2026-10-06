"""Importa Server/app.py de verdad (LabRem stubbeado, SQLite) para cubrir el pegamento."""
import functools
import importlib
import sys

import pytest

pytest.importorskip("flask_sqlalchemy")

import lease.wiring  # noqa: E402
from lease.history import HistoryRecorder  # noqa: E402
from lease.models import LeaseState  # noqa: E402
from tests.appkit import wait_until  # noqa: E402
from tests.fakes import RoutesLabRem  # noqa: E402


@pytest.fixture
def real_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{tmp_path / 'smoke.db'}")
    monkeypatch.setenv("JWT_KEY", "smoke-test-secret-smoke-test-secret-01")
    monkeypatch.setenv("JWT_LIFETIME_S", "7200")
    monkeypatch.setenv("LEASE_LOCK_FILE", str(tmp_path / "lease.lock"))
    # Las tablas se crean después del import: backoff corto para el primer intento fallido.
    monkeypatch.setattr(
        lease.wiring, "HistoryRecorder",
        functools.partial(HistoryRecorder, retry_initial=0.02, retry_max=0.05),
    )
    lr = RoutesLabRem()
    monkeypatch.setitem(sys.modules, "LabRem", lr)
    monkeypatch.delitem(sys.modules, "app", raising=False)
    module = importlib.import_module("app")
    with module.app.app_context():
        module.db.create_all()
        module.db.session.add(module.User(username="alice", password="x"))
        module.db.session.add(module.User(username="root", password="x", role="admin"))
        module.db.session.commit()
    manager = module.app.extensions["lease_manager"]
    assert wait_until(lambda: manager.status().state is LeaseState.FREE)
    yield module, lr, manager
    manager.stop()
    module.app.extensions["lease_process_lock"].release()
    sys.modules.pop("app", None)


def login(client, username):
    r = client.post("/", json={"username": username})
    return r


def test_app_wires_lease_hardware_and_login(real_app):
    module, lr, manager = real_app
    client = module.app.test_client()
    assert lr.connected is True

    assert login(client, "ghost").status_code == 401
    token = login(client, "alice").get_json()["token"]
    jwt_h = {"Authorization": f"Bearer {token}"}

    grant = client.post("/resource/acquire", headers=jwt_h).get_json()
    lease_h = {"X-Lease-Token": grant["lease_token"]}
    r = client.post("/inclinar", headers=lease_h, data={"angulo": "5"})
    assert r.status_code == 200
    assert client.post("/inclinar", headers=jwt_h, data={"angulo": "5"}).status_code == 401

    assert client.get("/resource/status").get_json()["state"] == "LOCKED"
    assert client.post("/resource/release", headers=lease_h).status_code == 200
    assert wait_until(lambda: client.get("/resource/status").get_json()["state"] == "FREE")


def test_login_no_longer_blocks_when_resource_is_busy(real_app):
    module, _, _ = real_app
    client = module.app.test_client()
    h = {"Authorization": "Bearer " + login(client, "alice").get_json()["token"]}
    client.post("/resource/acquire", headers=h)
    assert login(client, "alice").status_code == 200  # antes: 400 "Laboratorio ocupado"


def test_admin_role_comes_from_the_database(real_app):
    module, _, manager = real_app
    client = module.app.test_client()
    alice = {"Authorization": "Bearer " + login(client, "alice").get_json()["token"]}
    root = {"Authorization": "Bearer " + login(client, "root").get_json()["token"]}
    client.post("/resource/acquire", headers=alice)

    assert client.post("/admin/resource/force-release", headers=alice).status_code == 403
    assert manager.status().state is LeaseState.LOCKED
    assert client.post("/admin/resource/force-release", headers=root).get_json() == {
        "status": "forced"
    }
    assert wait_until(lambda: manager.status().state is LeaseState.FREE)


def test_old_mechanism_endpoints_are_gone(real_app):
    client = real_app[0].app.test_client()
    for path in ("/verificar_token", "/verificar_estado", "/change-state", "/hard-reset"):
        assert client.get(path).status_code == 404, path


def test_jwt_lifetime_comes_from_settings(real_app):
    module = real_app[0]
    assert module.app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds() == 7200


def test_lease_history_is_written_to_the_database(real_app):
    module, _, _ = real_app
    client = module.app.test_client()
    h = {"Authorization": "Bearer " + login(client, "alice").get_json()["token"]}
    grant = client.post("/resource/acquire", headers=h).get_json()
    client.post("/resource/release", headers={"X-Lease-Token": grant["lease_token"]})

    def row():
        with module.app.app_context():
            return module.LeaseHistory.query.first()

    assert wait_until(lambda: row() is not None and row().safe_state_ok is True)
    r = row()
    assert (r.username, r.end_reason) == ("alice", "released")


def test_app_refuses_a_second_process(real_app):
    from lease.process_lock import ProcessLock, ProcessLockError

    module = real_app[0]
    with pytest.raises(ProcessLockError):
        ProcessLock(module.app.extensions["lease_process_lock"]._path).acquire()


def test_healthz_is_exposed(real_app):
    client = real_app[0].app.test_client()
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["lease_state"] == "FREE"
