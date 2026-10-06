import threading

import pytest

from hardware.fake import FakeDriver
from lease.models import LeaseState
from tests.appkit import build_app, lease_headers, wait_until
from tests.fakes import FakeHistoryStore


@pytest.fixture
def built():
    envs = []

    def factory(**kw):
        env = build_app(**kw)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        if env.driver.safe_state_gate is not None:
            env.driver.safe_state_gate.set()
        env.manager.stop()
        history = env.app.extensions.get("lease_history")
        if history:
            history.stop()


def hung_driver():
    """Driver cuyo safe_state queda colgado (pero el de arranque ya terminó)."""
    return FakeDriver()


def arm_gate(env):
    env.driver.safe_state_gate = threading.Event()
    env.driver.safe_state_entered.clear()


# ----------------------------------------------------- release asíncrono (HTTP)
def test_release_responds_200_immediately_while_hardware_resets(built):
    env = built(async_reset=True)
    grant = env.acquire()
    arm_gate(env)

    r = env.client.post("/resource/release", headers=lease_headers(grant))
    assert r.status_code == 200
    assert r.get_json() == {"status": "released"}

    assert env.driver.safe_state_entered.wait(2)
    assert env.client.get("/resource/status").get_json()["state"] == "RESETTING"
    # el lease ya está revocado aunque la base siga reiniciándose
    hb = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert hb.status_code == 401 and hb.get_json()["reason"] == "released"
    assert env.client.post("/inclinar", headers=lease_headers(grant), data={"angulo": "5"}).status_code == 401
    # y nadie más puede entrar hasta que termine
    assert env.client.post("/resource/acquire", headers=env.jwt("bob")).status_code == 423

    env.driver.safe_state_gate.set()
    assert wait_until(lambda: env.client.get("/resource/status").get_json()["state"] == "FREE")
    assert env.client.post("/resource/acquire", headers=env.jwt("bob")).status_code == 200


def test_force_release_responds_immediately(built):
    env = built(async_reset=True)
    env.acquire()
    arm_gate(env)
    r = env.client.post("/admin/resource/force-release", headers=env.jwt("admin"))
    assert r.status_code == 200 and r.get_json() == {"status": "forced"}
    assert env.driver.safe_state_entered.wait(2)
    assert env.manager.status().state is LeaseState.RESETTING


def test_expired_lease_heartbeat_returns_401_without_waiting(built):
    env = built(async_reset=True)
    grant = env.acquire()
    arm_gate(env)
    env.clock.advance(1000)
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.status_code == 401 and r.get_json()["reason"] == "expired"
    assert env.client.get("/resource/status").get_json()["state"] == "RESETTING"


# ------------------------------------------------------------------ /healthz
def test_healthz_ok_when_free_and_locked(built):
    env = built()
    r = env.client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "lease_state": "FREE", "history": None}
    env.acquire("alice")
    r = env.client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["lease_state"] == "LOCKED"
    assert "alice" not in r.get_data(as_text=True)


def test_healthz_is_200_while_resetting(built):
    env = built(async_reset=True)
    grant = env.acquire()
    arm_gate(env)
    env.client.post("/resource/release", headers=lease_headers(grant))
    assert env.driver.safe_state_entered.wait(2)
    r = env.client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["lease_state"] == "RESETTING"


def test_healthz_503_when_fault(built):
    driver = FakeDriver()
    driver.failures_remaining = 1
    env = built(driver=driver, async_reset=True, wait_free=False)
    assert wait_until(lambda: env.manager.status().state is LeaseState.FAULT)
    r = env.client.get("/healthz")
    assert r.status_code == 503
    assert r.get_json()["status"] == "fault" and r.get_json()["lease_state"] == "FAULT"


def test_healthz_reports_history_counters(built):
    store = FakeHistoryStore()
    store.fail_upsert = True
    env = built(history_store=store)
    grant = env.acquire("alice")
    env.client.post("/resource/release", headers=lease_headers(grant))
    body = env.client.get("/healthz").get_json()
    assert body["history"] == {"pending": 1, "dropped": 0}
