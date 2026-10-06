from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from .errors import LeaseInvalid, LeaseRevoked, ResourceBusy, ResourceFault
from .history import serialize_record
from .models import LeaseState

LEASE_HEADER = "X-Lease-Token"

resource_bp = Blueprint("resource", __name__, url_prefix="/resource")
admin_bp = Blueprint("resource_admin", __name__, url_prefix="/admin/resource")
health_bp = Blueprint("health", __name__)


def _manager():
    return current_app.extensions["lease_manager"]


def lease_required(view):
    """Exige un lease válido (header X-Lease-Token) e inyecta `lease` (LeaseContext).

    Cuenta como señal de vida, igual que el heartbeat.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        ctx = _manager().validate(request.headers.get(LEASE_HEADER))
        return view(*args, lease=ctx, **kwargs)

    return wrapper


def _token_from_header_or_body():
    token = request.headers.get(LEASE_HEADER)
    if token:
        return token
    # navigator.sendBeacon no permite headers custom: el token viaja en el body,
    # normalmente como text/plain, por eso se fuerza el parseo JSON.
    data = request.get_json(force=True, silent=True)
    if isinstance(data, dict) and isinstance(data.get("lease_token"), str):
        return data["lease_token"]
    return request.form.get("lease_token")


@resource_bp.post("/acquire")
@jwt_required()
def acquire():
    grant = _manager().acquire(str(get_jwt_identity()))
    return jsonify(
        lease_token=grant.lease_token,
        stream_token=grant.stream_token,
        expires_in=grant.expires_in,
        heartbeat_every=grant.heartbeat_every,
        heartbeat_timeout=grant.heartbeat_timeout,
    )


@resource_bp.post("/heartbeat")
def heartbeat():
    remaining = _manager().renew(request.headers.get(LEASE_HEADER))
    return jsonify(seconds_remaining=remaining)


@resource_bp.post("/release")
def release():
    _manager().release(_token_from_header_or_body())
    return jsonify(status="released")


@resource_bp.get("/status")
def status():
    snapshot = _manager().status()
    return jsonify(
        state=snapshot.state.value,
        available=snapshot.available,
        available_in_seconds=snapshot.available_in_seconds,
    )


@admin_bp.post("/force-release")
@jwt_required()
def force_release():
    is_admin = current_app.extensions["lease_is_admin"]
    if not is_admin(str(get_jwt_identity())):
        return jsonify(error="forbidden"), 403
    acted = _manager().force_release()
    return jsonify(status="forced" if acted else "noop")


@admin_bp.get("/history")
@jwt_required()
def history():
    is_admin = current_app.extensions["lease_is_admin"]
    if not is_admin(str(get_jwt_identity())):
        return jsonify(error="forbidden"), 403
    recorder = current_app.extensions.get("lease_history")
    if recorder is None:
        return jsonify(error="history_disabled"), 404
    limit = max(1, min(request.args.get("limit", 50, type=int), 500))
    pending = {r["lease_id"]: r for r in recorder.pending_records()}
    try:
        rows = {r["lease_id"]: r for r in recorder.recent(limit)}
    except Exception:
        current_app.logger.exception("no se pudo leer el historial de leases")
        return jsonify(error="history_unavailable", pending_in_memory=len(pending)), 503
    rows.update(pending)  # lo pendiente en memoria es más reciente que lo guardado
    ordered = sorted(
        rows.values(), key=lambda r: r["acquired_at"].isoformat() if r["acquired_at"] else "",
        reverse=True,
    )[:limit]
    items = [dict(serialize_record(r), persisted=r["lease_id"] not in pending) for r in ordered]
    return jsonify(items=items, pending_in_memory=len(pending), dropped=recorder.dropped_count)


@health_bp.get("/healthz")
def healthz():
    """Salud del servicio: 503 solo si el hardware quedó en FAULT (para monitoreo)."""
    state = _manager().status().state
    recorder = current_app.extensions.get("lease_history")
    fault = state is LeaseState.FAULT
    body = {
        "status": "fault" if fault else "ok",
        "lease_state": state.value,
        "history": (
            {"pending": recorder.pending_count, "dropped": recorder.dropped_count}
            if recorder is not None
            else None
        ),
    }
    return jsonify(body), (503 if fault else 200)


def register_error_handlers(app):
    @app.errorhandler(LeaseInvalid)
    def _lease_invalid(e):
        return jsonify(error="lease_invalid", reason=e.reason.value), 401

    @app.errorhandler(LeaseRevoked)
    def _lease_revoked(e):
        # El lease terminó mientras el comando esperaba el hardware.
        reason = _manager().reason_for(request.headers.get(LEASE_HEADER))
        return jsonify(error="lease_invalid", reason=reason.value), 401

    @app.errorhandler(ResourceBusy)
    def _busy(e):
        response = jsonify(error="resource_busy", available_in_seconds=e.available_in)
        response.status_code = 423
        response.headers["Retry-After"] = str(max(1, e.available_in))
        return response

    @app.errorhandler(ResourceFault)
    def _fault(e):
        return jsonify(error="resource_fault"), 503
