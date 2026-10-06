import threading

import pytest

from lease.models import LeaseState
from tests.appkit import build_app, lease_headers, wait_until
from tests.fakes import FakeReader

ENDPOINTS = [
    ("post", "/inclinar"),
    ("get", "/iniciar"),
    ("get", "/reiniciar"),
    ("get", "/grafica-sensores"),
    ("get", "/resultados/grafica-aceleracion"),
    ("get", "/resultados/grafica-velocidad"),
    ("get", "/resultados/grafica-espacio"),
]


@pytest.fixture
def built():
    envs = []

    def factory(**kw):
        env = build_app(**kw)
        envs.append(env)
        return env

    yield factory
    for env in envs:
        if env.lr.gate is not None:
            env.lr.gate.set()
        env.manager.stop()


@pytest.fixture
def env(built):
    return built()


def call(env, method, path, grant=None, **kw):
    headers = lease_headers(grant) if grant else {}
    return getattr(env.client, method)(path, headers=headers, **kw)


# ------------------------------------------------------------- auth / lease
@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_every_hardware_endpoint_requires_a_lease(env, method, path):
    r = call(env, method, path)
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "unknown"}
    assert env.lr.calls == []


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_every_hardware_endpoint_rejects_a_released_lease(env, method, path):
    grant = env.acquire()
    env.client.post("/resource/release", headers=lease_headers(grant))
    r = call(env, method, path, grant)
    assert r.status_code == 401
    assert r.get_json() == {"error": "lease_invalid", "reason": "released"}
    assert env.lr.calls == []


def test_jwt_alone_is_not_enough_for_hardware(env):
    r = env.client.post("/inclinar", headers=env.jwt("alice"), data={"angulo": "5"})
    assert r.status_code == 401
    assert env.lr.calls == []


# ----------------------------------------------------------------- inclinar
def test_inclinar_ok(env):
    grant = env.acquire()
    r = call(env, "post", "/inclinar", grant, data={"angulo": "10"})
    assert r.status_code == 200
    assert r.get_json() == {"msg": "Base Inclinada"}
    assert env.lr.calls == ["ang 10.0"]


@pytest.mark.parametrize("value", ["20", "-1", "abc"])
def test_inclinar_invalid_angle_is_400_e02(env, value):
    grant = env.acquire()
    r = call(env, "post", "/inclinar", grant, data={"angulo": value})
    assert r.status_code == 400
    assert r.get_json()["code"] == "E02"
    assert isinstance(r.get_json()["msg"], str)
    assert env.lr.calls == []


def test_inclinar_timeout_is_504_e03_with_string_msg(env):
    env.lr.outcome = "timeout"
    grant = env.acquire()
    r = call(env, "post", "/inclinar", grant, data={"angulo": "5"})
    assert r.status_code == 504
    assert r.get_json() == {"msg": "Tiempo de espera agotado", "code": "E03"}


def test_inclinar_base_not_ready_is_400_e01(env):
    env.lr.estado_base = "Iniciando Exp..."
    grant = env.acquire()
    r = call(env, "post", "/inclinar", grant, data={"angulo": "5"})
    assert r.status_code == 400
    assert r.get_json() == {"msg": "Error al enviar comando", "code": "E01"}
    assert env.lr.calls == []


def test_inclinar_command_rejected_is_400(env):
    env.lr.outcome = "fail"
    grant = env.acquire()
    r = call(env, "post", "/inclinar", grant, data={"angulo": "5"})
    assert r.status_code == 400
    assert r.get_json() == {"msg": "Error al enviar comando"}


# ---------------------------------------------------------- iniciar/reiniciar
@pytest.mark.parametrize(
    "path,command,ok_msg,fail",
    [
        ("/iniciar", "com1", "Experimento realizado con éxito", {"msg": "Error al enviar comando", "code": "E01"}),
        ("/reiniciar", "com4", "Reiniciado correctamente", {"msg": "Ha ocurrido un error", "code": "E01"}),
    ],
)
def test_iniciar_and_reiniciar_outcomes(env, path, command, ok_msg, fail):
    grant = env.acquire()
    r = call(env, "get", path, grant)
    assert (r.status_code, r.get_json()) == (200, {"msg": ok_msg})
    assert env.lr.calls == [command]

    env.lr.outcome = "fail"
    r = call(env, "get", path, grant)
    assert (r.status_code, r.get_json()) == (400, fail)

    env.lr.outcome = "timeout"
    r = call(env, "get", path, grant)
    assert r.status_code == 504
    assert r.get_json()["code"] == "E03"
    assert isinstance(r.get_json()["msg"], str)


# ------------------------------------------------------------------ gráficos
@pytest.mark.parametrize(
    "path,tag",
    [
        ("/grafica-sensores", b"sensores"),
        ("/resultados/grafica-aceleracion", b"accel"),
        ("/resultados/grafica-velocidad", b"vel"),
        ("/resultados/grafica-espacio", b"esp"),
    ],
)
def test_graphs_return_materialized_png(env, path, tag):
    grant = env.acquire()
    r = call(env, "get", path, grant)
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    assert r.data == b"PNG-fake-" + tag


# ---------------------------------------------------------- fencing por HTTP
def test_inflight_command_blocks_safe_state_and_next_request_is_revoked(built):
    env = built()
    env.lr.gate = threading.Event()
    grant = env.acquire()
    results = {}

    def long_request():
        results["iniciar"] = env.app.test_client().get("/iniciar", headers=lease_headers(grant))

    t1 = threading.Thread(target=long_request)
    t1.start()
    assert env.lr.entered.wait(2)

    admin = threading.Thread(
        target=lambda: env.app.test_client().post(
            "/admin/resource/force-release", headers=env.jwt("admin")
        )
    )
    admin.start()
    assert wait_until(lambda: env.manager.status().state is LeaseState.RESETTING)

    # Mientras el comando sigue en vuelo, safe_state no pudo entrar al hardware.
    assert env.driver.safe_state_calls == 1  # solo el de arranque
    r = call(env, "get", "/reiniciar", grant)
    assert r.status_code == 401
    assert r.get_json()["reason"] == "forced"
    assert env.lr.calls == ["com1"]  # el comando posterior jamás se ejecutó

    env.lr.gate.set()
    t1.join(3)
    admin.join(3)
    assert results["iniciar"].status_code == 200  # el comando en vuelo terminó normalmente
    assert env.manager.status().state is LeaseState.FREE
    assert env.driver.safe_state_calls == 2


# -------------------------------------------------------------------- cámara
def test_camera_requires_valid_stream_token(env):
    grant = env.acquire()
    assert env.client.get("/camera").status_code == 401
    assert env.client.get("/camera?t=nope").status_code == 401
    # el lease token NO sirve como ticket de cámara
    assert env.client.get(f"/camera?t={grant['lease_token']}").status_code == 401


def test_camera_streams_frames_with_proper_headers(built):
    readers = []

    def factory():
        readers.append(FakeReader())
        return readers[-1]

    env = built(reader_factory=factory)
    grant = env.acquire()
    r = env.client.get(f"/camera?t={grant['stream_token']}", buffered=False)
    assert r.status_code == 200
    assert r.mimetype == "multipart/x-mixed-replace"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Accel-Buffering"] == "no"
    first = next(iter(r.response))
    assert first.startswith(b"--frame\r\nContent-Type: image/webp")
    r.close()


def test_camera_stops_when_lease_ends_and_closes_reader(built):
    readers = []

    def factory():
        readers.append(FakeReader())
        return readers[-1]

    env = built(reader_factory=factory)
    grant = env.acquire()
    r = env.client.get(f"/camera?t={grant['stream_token']}", buffered=False)
    stream = iter(r.response)
    next(stream)
    env.client.post("/resource/release", headers=lease_headers(grant))
    with pytest.raises(StopIteration):
        next(stream)
    assert readers[0].closed is True


def test_camera_closes_reader_when_client_disconnects(built):
    readers = []

    def factory():
        readers.append(FakeReader())
        return readers[-1]

    env = built(reader_factory=factory)
    grant = env.acquire()
    r = env.client.get(f"/camera?t={grant['stream_token']}", buffered=False)
    next(iter(r.response))
    r.close()  # el cliente corta la conexión
    assert readers[0].closed is True


def test_camera_stream_token_dies_with_the_lease(env):
    grant = env.acquire()
    env.client.post("/resource/release", headers=lease_headers(grant))
    assert env.client.get(f"/camera?t={grant['stream_token']}").status_code == 401
