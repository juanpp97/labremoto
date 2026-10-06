from datetime import datetime, timezone
from typing import List


def _naive_utc(value):
    """DATETIME de MySQL es naive: se guarda siempre en UTC."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _aware_utc(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_sql_history(db, app):
    """Define el modelo `lease_history` sobre `db` y devuelve (Modelo, store).

    Llamar una sola vez por instancia de `db` (registra la tabla en su metadata).
    El store usa `app.app_context()`, así que puede invocarse desde cualquier hilo.
    """

    class LeaseHistory(db.Model):
        __tablename__ = "lease_history"
        lease_id = db.Column(db.String(36), primary_key=True)
        username = db.Column(db.String(80), nullable=False)
        acquired_at = db.Column(db.DateTime, nullable=False, index=True)
        ended_at = db.Column(db.DateTime, nullable=True)
        end_reason = db.Column(db.String(20), nullable=True)
        safe_state_ok = db.Column(db.Boolean, nullable=True)
        safe_state_ms = db.Column(db.Integer, nullable=True)

    class SqlHistoryStore:
        def upsert(self, record: dict) -> None:
            values = {k: _naive_utc(v) for k, v in record.items()}
            with app.app_context():
                try:
                    db.session.merge(LeaseHistory(**values))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise

        def close_orphans(self, before: datetime, ended_at: datetime) -> int:
            with app.app_context():
                try:
                    closed = (
                        LeaseHistory.query.filter(
                            LeaseHistory.ended_at.is_(None),
                            LeaseHistory.acquired_at < _naive_utc(before),
                        ).update(
                            {
                                "ended_at": _naive_utc(ended_at),
                                "end_reason": "server_restart",
                            },
                            synchronize_session=False,
                        )
                    )
                    db.session.commit()
                    return closed
                except Exception:
                    db.session.rollback()
                    raise

        def recent(self, limit: int) -> List[dict]:
            with app.app_context():
                rows = (
                    LeaseHistory.query.order_by(LeaseHistory.acquired_at.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "lease_id": r.lease_id,
                        "username": r.username,
                        "acquired_at": _aware_utc(r.acquired_at),
                        "ended_at": _aware_utc(r.ended_at),
                        "end_reason": r.end_reason,
                        "safe_state_ok": r.safe_state_ok,
                        "safe_state_ms": r.safe_state_ms,
                    }
                    for r in rows
                ]

    return LeaseHistory, SqlHistoryStore()
