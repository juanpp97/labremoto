import time
from datetime import datetime, timedelta, timezone

import pytest

from lease.models import LeaseState
from tests.appkit import build_app, lease_headers, wait_until
from tests.fakes import FakeHistoryStore

flask = pytest.importorskip("flask")
pytest.importorskip("flask_sqlalchemy")

from flask import Flask  # noqa: E402
from flask_sqlalchemy import SQLAlchemy  # noqa: E402

from lease.sql_history import build_sql_history  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def record(lease_id, acquired=T0, **kw):
    base = {
        "lease_id": lease_id, "username": "alice", "acquired_at": acquired, "ended_at": None,
        "end_reason": None, "safe_state_ok": None, "safe_state_ms": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def sql(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'history.db'}"
    db = SQLAlchemy(app)
    Model, store = build_sql_history(db, app)
    with app.app_context():
        db.create_all()
    yield store, Model, app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


# ------------------------------------------------------------------- store SQL
def test_upsert_inserts_then_updates_the_same_row(sql):
    store, Model, app = sql
    store.upsert(record("L1"))
    store.upsert(
        record("L1", ended_at=T0 + timedelta(seconds=90), end_reason="released",
               safe_state_ok=True, safe_state_ms=250)
    )
    rows = store.recent(10)
    assert len(rows) == 1
    row = rows[0]
    assert row["ended_at"] == T0 + timedelta(seconds=90)
    assert (row["end_reason"], row["safe_state_ok"], row["safe_state_ms"]) == ("released", True, 250)
    assert row["acquired_at"].tzinfo is not None  # vuelve como UTC aware


def test_recent_is_newest_first_and_respects_limit(sql):
    store, _, _ = sql
    for i in range(3):
        store.upsert(record(f"L{i}", acquired=T0 + timedelta(minutes=i)))
    assert [r["lease_id"] for r in store.recent(2)] == ["L2", "L1"]


def test_close_orphans_only_closes_open_leases_before_boot(sql):
    store, _, _ = sql
    boot = T0 + timedelta(hours=1)
    store.upsert(record("orphan", acquired=T0))
    store.upsert(record("done", acquired=T0, ended_at=T0 + timedelta(seconds=5), end_reason="released"))
    store.upsert(record("new", acquired=boot + timedelta(seconds=1)))
    closed = store.close_orphans(boot, boot + timedelta(seconds=2))
    assert closed == 1
    by_id = {r["lease_id"]: r for r in store.recent(10)}
    assert by_id["orphan"]["end_reason"] == "server_restart"
    assert by_id["orphan"]["ended_at"] == boot + timedelta(seconds=2)
    assert by_id["done"]["end_reason"] == "released"
    assert by_id["new"]["ended_at"] is None


# ---------------------------------------------------------- endpoint admin
@pytest.fixture
def built():
    envs = []

    def factory(**kw):
        env = build_app(**kw)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        env.manager.stop()
        if env.app.extensions.get("lease_history"):
            env.app.extensions["lease_history"].stop()


def full_cycle(env, user):
    grant = env.acquire(user)
    env.client.post("/resource/release", headers=lease_headers(grant))


def history(env, user="admin", **params):
    return env.client.get("/admin/resource/history", headers=env.jwt(user), query_string=params)


def test_history_endpoint_end_to_end_with_sql_store(built, sql):
    store, _, _ = sql
    env = built(history_store=store)
    full_cycle(env, "alice")
    assert wait_until(lambda: env.app.extensions["lease_history"].pending_count == 0)

    r = history(env)
    assert r.status_code == 200
    body = r.get_json()
    assert body["pending_in_memory"] == 0 and body["dropped"] == 0
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["username"] == "alice"
    assert item["end_reason"] == "released"
    assert item["safe_state_ok"] is True
    assert item["persisted"] is True
    assert item["acquired_at"].endswith("+00:00") and item["ended_at"]


def test_history_requires_admin(built):
    env = built(history_store=FakeHistoryStore())
    assert env.client.get("/admin/resource/history").status_code == 401
    r = env.client.get("/admin/resource/history", headers=env.jwt("alice"))
    assert r.status_code == 403


def test_history_disabled_when_no_store_configured(built):
    env = built()
    assert history(env).status_code == 404
    assert history(env).get_json() == {"error": "history_disabled"}


def test_history_limit_and_order(built):
    store = FakeHistoryStore()
    env = built(history_store=store)
    for user in ("alice", "bob", "carol"):
        full_cycle(env, user)
        time.sleep(0.02)
    assert wait_until(lambda: env.app.extensions["lease_history"].pending_count == 0)
    items = history(env, limit=2).get_json()["items"]
    assert [i["username"] for i in items] == ["carol", "bob"]


def test_history_shows_unpersisted_records_when_db_writes_fail(built):
    store = FakeHistoryStore()
    store.fail_upsert = True
    env = built(history_store=store)
    full_cycle(env, "alice")
    body = history(env).get_json()
    assert body["pending_in_memory"] == 1
    assert body["items"][0]["username"] == "alice"
    assert body["items"][0]["persisted"] is False
    store.fail_upsert = False
    assert wait_until(lambda: env.app.extensions["lease_history"].pending_count == 0)
    assert history(env).get_json()["items"][0]["persisted"] is True


def test_history_503_when_db_unreadable_but_reports_pending(built):
    store = FakeHistoryStore()
    store.fail_upsert = True
    store.fail_recent = True
    env = built(history_store=store)
    full_cycle(env, "alice")
    r = history(env)
    assert r.status_code == 503
    assert r.get_json() == {"error": "history_unavailable", "pending_in_memory": 1}


def test_db_failure_never_affects_the_lease_flow(built):
    store = FakeHistoryStore()
    store.fail_upsert = True
    store.fail_orphans = True
    env = built(history_store=store)
    grant = env.acquire("alice")
    assert env.client.post("/inclinar", headers=lease_headers(grant), data={"angulo": "5"}).status_code == 200
    env.client.post("/resource/release", headers=lease_headers(grant))
    assert env.manager.status().state is LeaseState.FREE
    assert env.client.get("/resource/status").get_json()["available"] is True
