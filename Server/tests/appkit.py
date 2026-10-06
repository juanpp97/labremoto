"""Mini-app Flask con JWT + lease + rutas de hardware sobre fakes, para tests de API."""
import time
from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from hardware.fake import FakeDriver
from hardware.routes import create_hardware_blueprint
from lease.clock import FakeClock
from lease.models import LeaseState
from lease.settings import LeaseSettings
from lease.wiring import setup_resource
from tests.fakes import RoutesLabRem, inline_runner

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


def build_app(
    lr=None, reader_factory=None, history_store=None, driver=None, history_options=None,
    async_reset=False, wait_free=True,
):
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "test-secret-key-test-secret-key-0123"
    JWTManager(app)
    clock = FakeClock()
    driver = driver or FakeDriver()
    lr = lr or RoutesLabRem()
    settings = LeaseSettings(
        lease_duration=DURATION, heartbeat_every=20, heartbeat_timeout=HB_TIMEOUT,
        watchdog_tick=60, safe_state_retry_initial=60, safe_state_retry_max=60,
    )
    kwargs = {}
    if history_store is not None:
        kwargs = {
            "history_store": history_store,
            "history_options": history_options or {"retry_initial": 0.01, "retry_max": 0.02},
        }
    manager, hardware = setup_resource(
        app, driver, settings, is_admin=lambda u: u in ADMINS, clock=clock,
        register_atexit=False, reset_runner=None if async_reset else inline_runner, **kwargs,
    )
    app.register_blueprint(
        create_hardware_blueprint(
            lr, camera_reader_factory=reader_factory, frame_rate=1000, experiment_wait=0
        )
    )

    def jwt_headers(user):
        with app.app_context():
            return {"Authorization": f"Bearer {create_access_token(identity=user)}"}

    env = SimpleNamespace(
        app=app, client=app.test_client(), clock=clock, driver=driver, lr=lr,
        manager=manager, jwt=jwt_headers,
    )

    def acquire(user="alice", client=None):
        r = (client or env.client).post("/resource/acquire", headers=jwt_headers(user))
        assert r.status_code == 200, r.get_data(as_text=True)
        return r.get_json()

    env.acquire = acquire
    if wait_free:
        assert wait_until(lambda: manager.status().state is LeaseState.FREE)
    return env


def lease_headers(grant):
    return {"X-Lease-Token": grant["lease_token"]}
