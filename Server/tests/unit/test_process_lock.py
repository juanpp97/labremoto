import pytest
from flask import Flask
from flask_jwt_extended import JWTManager

from hardware.fake import FakeDriver
from lease.process_lock import ProcessLock, ProcessLockError, acquire_process_lock
from lease.settings import LeaseSettings
from lease.wiring import setup_resource
from tests.fakes import inline_runner


def test_second_process_fails_fast_with_a_clear_error(tmp_path):
    path = str(tmp_path / "lease.lock")
    first = ProcessLock(path)
    first.acquire()
    try:
        with pytest.raises(ProcessLockError, match="único proceso"):
            ProcessLock(path).acquire()
    finally:
        first.release()


def test_lock_is_released_and_can_be_taken_again(tmp_path):
    path = str(tmp_path / "lease.lock")
    first = ProcessLock(path)
    first.acquire()
    first.release()
    second = ProcessLock(path)
    second.acquire()
    second.release()


def test_acquire_and_release_are_idempotent(tmp_path):
    lock = ProcessLock(str(tmp_path / "lease.lock"))
    lock.acquire()
    lock.acquire()
    lock.release()
    lock.release()


def test_different_paths_do_not_conflict(tmp_path):
    a, b = ProcessLock(str(tmp_path / "a.lock")), ProcessLock(str(tmp_path / "b.lock"))
    a.acquire()
    b.acquire()
    a.release()
    b.release()


@pytest.mark.parametrize("path", [None, ""])
def test_guard_is_disabled_without_a_path(path):
    assert acquire_process_lock(path) is None


def _app():
    app = Flask(__name__)
    app.config["JWT_SECRET_KEY"] = "test-secret-key-test-secret-key-0123"
    JWTManager(app)
    return app


def test_setup_resource_refuses_a_second_instance_before_starting_anything(tmp_path):
    path = str(tmp_path / "lease.lock")
    settings = LeaseSettings(watchdog_tick=60)
    app1 = _app()
    manager, _ = setup_resource(
        app1, FakeDriver(), settings, register_atexit=False,
        reset_runner=inline_runner, process_lock_path=path,
    )
    try:
        app2 = _app()
        driver2 = FakeDriver()
        with pytest.raises(ProcessLockError):
            setup_resource(
                app2, driver2, settings, register_atexit=False,
                reset_runner=inline_runner, process_lock_path=path,
            )
        assert "lease_manager" not in app2.extensions  # no se creó nada
        assert driver2.safe_state_calls == 0  # y no se tocó el hardware
    finally:
        manager.stop()
        app1.extensions["lease_process_lock"].release()
