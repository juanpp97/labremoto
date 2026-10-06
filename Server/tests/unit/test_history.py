import threading
import time
from datetime import datetime, timedelta, timezone

from lease.history import HistoryRecorder, serialize_record
from lease.models import EndReason, EventKind, LeaseEvent
from tests.fakes import FakeHistoryStore

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def started(lease_id, user="alice", at=T0):
    return LeaseEvent(EventKind.STARTED, lease_id, at, user_id=user)


def ended(lease_id, reason=EndReason.RELEASED, at=T0 + timedelta(seconds=60)):
    return LeaseEvent(EventKind.ENDED, lease_id, at, user_id="alice", end_reason=reason)


def reset_done(lease_id, ok=True, ms=120):
    return LeaseEvent(EventKind.RESET_DONE, lease_id, T0, safe_state_ok=ok, safe_state_ms=ms)


def make(store=None, **kw):
    store = store or FakeHistoryStore()
    kw.setdefault("retry_initial", 0.01)
    kw.setdefault("retry_max", 0.02)
    recorder = HistoryRecorder(store, **kw)
    recorder.start()
    return store, recorder


def test_lifecycle_is_persisted_and_evicted_from_memory():
    store, rec = make()
    try:
        rec.record(started("L1"))
        assert wait_until(lambda: "L1" in store.rows and store.rows["L1"]["ended_at"] is None)
        assert store.rows["L1"]["username"] == "alice"
        rec.record(ended("L1"))
        rec.record(reset_done("L1"))
        assert wait_until(lambda: store.rows["L1"]["safe_state_ok"] is True)
        row = store.rows["L1"]
        assert row["end_reason"] == "released" and row["ended_at"] == T0 + timedelta(seconds=60)
        assert row["safe_state_ms"] == 120
        assert wait_until(lambda: rec.pending_count == 0)
    finally:
        rec.stop()


def test_db_down_keeps_records_in_memory_then_recovers_with_the_complete_record():
    store = FakeHistoryStore()
    store.fail_upsert = True
    store, rec = make(store)
    try:
        rec.record(started("L1"))
        rec.record(ended("L1", EndReason.EXPIRED))
        rec.record(reset_done("L1"))
        assert wait_until(lambda: store.upserts >= 2)  # reintenta
        assert store.rows == {} and rec.pending_count == 1
        assert rec.pending_records()[0]["end_reason"] == "expired"

        store.fail_upsert = False
        assert wait_until(lambda: "L1" in store.rows)
        row = store.rows["L1"]  # el registro llega completo aunque el started falló antes
        assert (row["username"], row["end_reason"], row["safe_state_ok"]) == ("alice", "expired", True)
        assert wait_until(lambda: rec.pending_count == 0)
    finally:
        rec.stop()


def test_memory_is_bounded_and_drops_oldest_finished_records():
    store = FakeHistoryStore()
    store.fail_upsert = True
    store, rec = make(store, max_pending=3)
    try:
        rec.record(started("open"))  # lease abierto: nunca se descarta
        for i in range(4):
            rec.record(started(f"c{i}"))
            rec.record(ended(f"c{i}"))
            rec.record(reset_done(f"c{i}"))
        ids = {r["lease_id"] for r in rec.pending_records()}
        assert len(ids) == 3 and "open" in ids
        assert rec.dropped_count == 2
        assert "c0" not in ids and "c1" not in ids
    finally:
        rec.stop()


def test_failed_safe_state_record_is_kept_and_updated_on_recovery():
    store, rec = make()
    try:
        rec.record(started("L1"))
        rec.record(ended("L1"))
        rec.record(reset_done("L1", ok=False))
        assert wait_until(lambda: store.rows.get("L1", {}).get("safe_state_ok") is False)
        rec.record(reset_done("L1", ok=True, ms=900))  # el reintento de FAULT tuvo éxito
        assert wait_until(lambda: store.rows["L1"]["safe_state_ok"] is True)
        assert store.rows["L1"]["safe_state_ms"] == 900
    finally:
        rec.stop()


def test_events_for_unknown_leases_are_ignored():
    store, rec = make()
    try:
        rec.record(reset_done("ghost"))
        rec.record(ended("ghost"))
        time.sleep(0.05)
        assert store.rows == {} and rec.pending_count == 0
    finally:
        rec.stop()


def test_orphans_are_closed_before_boot_time_and_before_any_write():
    store = FakeHistoryStore()
    store.fail_orphans = True
    boot = T0 - timedelta(hours=1)
    store, rec = make(store, boot_time=boot)
    try:
        rec.record(started("L1"))
        assert wait_until(lambda: len(store.orphan_calls) >= 2)  # reintenta
        assert store.rows == {}  # no se escribe nada hasta cerrar huérfanos
        store.fail_orphans = False
        assert wait_until(lambda: "L1" in store.rows)
        assert store.orphan_calls[-1][0] == boot
    finally:
        rec.stop()


def test_record_never_blocks_even_if_the_store_hangs():
    store = FakeHistoryStore()
    store.gate = threading.Event()
    store, rec = make(store)
    try:
        def burst():
            for i in range(200):
                rec.record(started(f"L{i}"))

        t = threading.Thread(target=burst)
        t.start()
        t.join(2)
        assert not t.is_alive(), "record() se bloqueó esperando a la DB"
    finally:
        store.gate.set()
        rec.stop()


def test_stop_performs_a_final_flush():
    store = FakeHistoryStore()
    rec = HistoryRecorder(store)  # sin start(): solo el flush final
    rec.record(started("L1"))
    rec.stop()
    assert "L1" in store.rows


def test_serialize_record_uses_iso_utc():
    out = serialize_record({"acquired_at": T0, "ended_at": None, "username": "alice"})
    assert out["acquired_at"] == "2026-01-01T12:00:00+00:00"
    assert out["ended_at"] is None
    naive = serialize_record({"acquired_at": T0.replace(tzinfo=None)})
    assert naive["acquired_at"] == "2026-01-01T12:00:00+00:00"
