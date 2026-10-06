import json
import threading
import time
from types import SimpleNamespace

import pytest
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, create_access_token

from hardware.fake import FakeDriver
from lease.clock import FakeClock
from lease.flask_api import lease_required
from lease.models import LeaseState
from lease.settings import LeaseSettings
from lease.wiring import setup_resource
from tests.fakes import inline_runner

DURATION = 900
HB_TIMEOUT = 75
ADMINS = {"admin"}


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def build(driver=None, retry_initial=60):
    """Mini-app con JWT + lease sobre FakeDriver y FakeClock."""
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "test-secret-key-test-secret-key-0123"
    JWTManager(app)
    clock = FakeClock()
    driver = driver or FakeDriver()
    settings = LeaseSettings(
        lease_duration=DURATION, heartbeat_every=20, heartbeat_timeout=HB_TIMEOUT,
        watchdog_tick=60, safe_state_retry_initial=retry_initial, safe_state_retry_max=retry_initial,
    )
    manager, hardware = setup_resource(
        app, driver, settings, is_admin=lambda u: u in ADMINS, clock=clock,
        register_atexit=False, reset_runner=inline_runner,
    )

    @app.post("/_probe")
    @lease_required
    def probe(lease):
        return jsonify(result=hardware.run(lease, lambda: "moved"))

    @app.post("/_probe_revoked")
    @lease_required
    def probe_revoked(lease):
        manager.release(lease.token)  # el lease termina antes de llegar al hardware
        return jsonify(result=hardware.run(lease, lambda: "moved"))

    def jwt_headers(user):
        with app.app_context():
            return {"Authorization": f"Bearer {create_access_token(identity=user)}"}

    return SimpleNamespace(
        app=app, client=app.test_client(), clock=clock, driver=driver,
        manager=manager, jwt=jwt_headers,
    )


@pytest.fixture
def built():
    envs = []

    def factory(**kw):
        env = build(**kw)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        if env.driver.safe_state_gate is not None:
            env.driver.safe_state_gate.set()
        env.manager.stop()


@pytest.fixture
def env(built):
    e = built()
    assert wait_until(lambda: e.manager.status().state is LeaseState.FREE)
    return e


def acquire(env, user="alice"):
    r = env.client.post("/resource/acquire", headers=env.jwt(user))
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def lease_headers(grant):
    return {"X-Lease-Token": grant["lease_token"]}


# ------------------------------------------------------------------ acquire
def test_acquire_200_body(env):
    body = acquire(env)
    assert set(body) == {
        "lease_token", "stream_token", "expires_in", "heartbeat_every", "heartbeat_timeout",
    }
    assert body["expires_in"] == DURATION
    assert body["heartbeat_every"] == 20
    assert body["heartbeat_timeout"] == HB_TIMEOUT


def test_acquire_requires_jwt(env):
    assert env.client.post("/resource/acquire").status_code == 401


def test_acquire_other_user_423_with_retry_after(env):
    acquire(env, "alice")
    env.clock.advance(50)
    r = env.client.post("/resource/acquire", headers=env.jwt("bob"))
    assert r.status_code == 423
    assert r.get_json() == {"error": "resource_busy", "available_in_seconds": DURATION - 50}
    assert r.headers["Retry-After"] == str(DURATION - 50)


def test_reacquire_same_user_returns_same_lease(env):
    first = acquire(env, "alice")
    again = acquire(env, "alice")
    assert again["lease_token"] == first["lease_token"]
    assert again["stream_token"] == first["stream_token"]


def test_acquire_503_when_fault(built):
    driver = FakeDriver()
    driver.failures_remaining = 1
    e = built(driver=driver)
    assert wait_until(lambda: e.manager.status().state is LeaseState.FAULT)
    r = e.client.post("/resource/acquire", headers=e.jwt("alice"))
    assert r.status_code == 503
    assert r.get_json() == {"error": "resource_fault"}


# ---------------------------------------------------------------- heartbeat
def test_heartbeat_200_seconds_remaining(env):
    grant = acquire(env)
    env.clock.advance(30)
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.status_code == 200
    assert r.get_json() == {"seconds_remaining": DURATION - 30}


def test_heartbeat_without_header_is_401_unknown(env):
    acquire(env)
    r = env.client.post("/resource/heartbeat")
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "unknown"}


def test_heartbeat_garbage_token_is_401_unknown(env):
    acquire(env)
    r = env.client.post("/resource/heartbeat", headers={"X-Lease-Token": "nope"})
    assert r.status_code == 401
    assert r.get_json()["reason"] == "unknown"


def test_heartbeat_reason_expired(env):
    grant = acquire(env)
    env.clock.advance(DURATION)
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "expired"}


def test_heartbeat_reason_heartbeat_timeout(env):
    grant = acquire(env)
    env.clock.advance(HB_TIMEOUT + 1)
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.get_json()["reason"] == "heartbeat_timeout"


def test_heartbeat_reason_released(env):
    grant = acquire(env)
    env.client.post("/resource/release", headers=lease_headers(grant))
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.status_code == 401
    assert r.get_json()["reason"] == "released"


def test_heartbeat_reason_forced(env):
    grant = acquire(env)
    r = env.client.post("/admin/resource/force-release", headers=env.jwt("admin"))
    assert r.status_code == 200
    r = env.client.post("/resource/heartbeat", headers=lease_headers(grant))
    assert r.get_json()["reason"] == "forced"


# ------------------------------------------------------------------ release
def test_release_by_header(env):
    grant = acquire(env)
    r = env.client.post("/resource/release", headers=lease_headers(grant))
    assert r.status_code == 200
    assert r.get_json() == {"status": "released"}
    assert env.manager.status().state is LeaseState.FREE
    assert env.driver.safe_state_calls == 2  # arranque + fin de sesión


def test_release_by_json_body(env):
    grant = acquire(env)
    r = env.client.post("/resource/release", json={"lease_token": grant["lease_token"]})
    assert r.status_code == 200
    assert env.manager.status().state is LeaseState.FREE


def test_release_by_text_plain_body_like_sendbeacon(env):
    grant = acquire(env)
    r = env.client.post(
        "/resource/release",
        data=json.dumps({"lease_token": grant["lease_token"]}),
        content_type="text/plain;charset=UTF-8",
    )
    assert r.status_code == 200
    assert env.manager.status().state is LeaseState.FREE


def test_release_invalid_token_is_401_and_keeps_lease(env):
    grant = acquire(env)
    r = env.client.post("/resource/release", json={"lease_token": "nope"})
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "unknown"}
    assert env.client.post("/resource/release").status_code == 401  # sin token
    assert env.client.post("/resource/heartbeat", headers=lease_headers(grant)).status_code == 200


# ------------------------------------------------------------------- status
def test_status_free(env):
    r = env.client.get("/resource/status")
    assert r.status_code == 200
    assert r.get_json() == {"state": "FREE", "available": True, "available_in_seconds": 0}


def test_status_locked_does_not_leak_user(env):
    acquire(env, "alice")
    env.clock.advance(100)
    r = env.client.get("/resource/status")
    assert r.get_json() == {
        "state": "LOCKED", "available": False, "available_in_seconds": DURATION - 100,
    }
    assert "alice" not in r.get_data(as_text=True)


def test_status_resetting_during_startup_then_free(built):
    driver = FakeDriver()
    driver.safe_state_gate = threading.Event()
    e = built(driver=driver)
    assert driver.safe_state_entered.wait(2)
    assert e.client.get("/resource/status").get_json()["state"] == "RESETTING"
    r = e.client.post("/resource/acquire", headers=e.jwt("alice"))
    assert r.status_code == 423
    driver.safe_state_gate.set()
    assert wait_until(lambda: e.client.get("/resource/status").get_json()["state"] == "FREE")
    assert driver.safe_state_calls == 1


def test_status_fault_when_startup_safe_state_fails(built):
    driver = FakeDriver()
    driver.failures_remaining = 1
    e = built(driver=driver)
    assert wait_until(lambda: e.client.get("/resource/status").get_json()["state"] == "FAULT")
    assert e.client.get("/resource/status").get_json() == {
        "state": "FAULT", "available": False, "available_in_seconds": None,
    }


# -------------------------------------------------------------------- admin
def test_force_release_requires_jwt(env):
    assert env.client.post("/admin/resource/force-release").status_code == 401


def test_force_release_forbidden_for_non_admin(env):
    acquire(env)
    r = env.client.post("/admin/resource/force-release", headers=env.jwt("alice"))
    assert r.status_code == 403
    assert env.manager.status().state is LeaseState.LOCKED


def test_force_release_admin_ends_lease_and_resets_hardware(env):
    acquire(env)
    r = env.client.post("/admin/resource/force-release", headers=env.jwt("admin"))
    assert r.status_code == 200
    assert r.get_json() == {"status": "forced"}
    assert env.manager.status().state is LeaseState.FREE
    assert env.driver.safe_state_calls == 2


def test_force_release_noop_when_free(env):
    r = env.client.post("/admin/resource/force-release", headers=env.jwt("admin"))
    assert r.get_json() == {"status": "noop"}


def test_force_release_in_fault_retries_safe_state(built):
    driver = FakeDriver()
    driver.failures_remaining = 1
    e = built(driver=driver)  # retry automático lento (60 s): lo dispara el admin
    assert wait_until(lambda: e.manager.status().state is LeaseState.FAULT)
    r = e.client.post("/admin/resource/force-release", headers=e.jwt("admin"))
    assert r.status_code == 200
    assert e.manager.status().state is LeaseState.FREE


# ------------------------------------------------------------ lease_required
def test_lease_required_rejects_without_lease(env):
    r = env.client.post("/_probe")
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "unknown"}


def test_lease_required_passes_context_to_hardware(env):
    grant = acquire(env)
    r = env.client.post("/_probe", headers=lease_headers(grant))
    assert r.status_code == 200
    assert r.get_json() == {"result": "moved"}


def test_lease_required_counts_as_heartbeat(env):
    grant = acquire(env)
    env.clock.advance(60)
    assert env.client.post("/_probe", headers=lease_headers(grant)).status_code == 200
    env.clock.advance(60)
    env.manager.tick()
    assert env.manager.status().state is LeaseState.LOCKED


def test_lease_required_401_with_reason_after_release(env):
    grant = acquire(env)
    env.client.post("/resource/release", headers=lease_headers(grant))
    r = env.client.post("/_probe", headers=lease_headers(grant))
    assert r.status_code == 401
    assert r.get_json()["reason"] == "released"


def test_lease_revoked_mid_request_maps_to_401_with_reason(env):
    grant = acquire(env)
    r = env.client.post("/_probe_revoked", headers=lease_headers(grant))
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "released"}
