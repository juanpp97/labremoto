import io
import time

from flask import Blueprint, Response, current_app, jsonify, request
from PIL import Image

from lease.flask_api import lease_required

EXPERIMENT_WAIT_S = 5.0
_NOT_READY = object()


def _default_reader_factory():
    import imageio as iio  # import tardío: solo hace falta con la cámara real

    return iio.get_reader("<video0>")


def create_hardware_blueprint(
    lr,
    camera_reader_factory=None,
    frame_rate=30,
    experiment_wait=EXPERIMENT_WAIT_S,
):
    """Rutas que operan el hardware. `lr` es el módulo LabRem (o un fake en tests).

    Todo acceso físico pasa por HardwareController.run (fencing por epoch).
    La cámara es otro dispositivo (webcam, no MQTT): se autoriza con el
    stream_token del lease y no pasa por el io_lock.
    """
    bp = Blueprint("hardware", __name__)
    reader_factory = camera_reader_factory or _default_reader_factory

    def _run(lease, op):
        return current_app.extensions["lease_hardware"].run(lease, op)

    @bp.post("/inclinar")
    @lease_required
    def inclinar(lease):
        angulo = request.form.get("angulo", 0)

        def op():
            if not lr.consultarEstado():
                return _NOT_READY
            return lr.enviarAnguloCin(angulo)

        try:
            res = _run(lease, op)
        except lr.AnguloInvalidoError as e:
            return jsonify(msg=str(e), code="E02"), 400
        except ValueError:
            return jsonify(msg="Ángulo Inválido", code="E02"), 400
        except lr.TimeOutError as e:
            return jsonify(msg=str(e), code="E03"), 504
        if res is _NOT_READY:
            return jsonify(msg="Error al enviar comando", code="E01"), 400
        if res:
            return jsonify(msg="Base Inclinada"), 200
        return jsonify(msg="Error al enviar comando"), 400

    @bp.get("/iniciar")
    @lease_required
    def iniciar(lease):
        def op():
            res = lr.iniExp()
            # La espera va dentro del op: safe_state no puede interrumpir el experimento.
            time.sleep(experiment_wait)
            return res

        try:
            res = _run(lease, op)
        except lr.TimeOutError as e:
            return jsonify(msg=str(e), code="E03"), 504
        if res:
            return jsonify(msg="Experimento realizado con éxito")
        return jsonify(msg="Error al enviar comando", code="E01"), 400

    @bp.get("/reiniciar")
    @lease_required
    def reiniciar(lease):
        try:
            res = _run(lease, lr.reinExp)
        except lr.TimeOutError as e:
            return jsonify(msg=str(e), code="E03"), 504
        if res:
            return jsonify(msg="Reiniciado correctamente")
        return jsonify(msg="Ha ocurrido un error", code="E01"), 400

    def _add_graph(rule, endpoint, func_name):
        @lease_required
        def view(lease):
            # Los gráficos son generadores: se materializan dentro del op para que
            # corran bajo el io_lock y con el lease verificado.
            data = _run(lease, lambda: b"".join(getattr(lr, func_name)()))
            return Response(data, mimetype="image/png")

        bp.add_url_rule(rule, endpoint, view)

    _add_graph("/grafica-sensores", "grafica_sensores", "GraficarDatos")
    _add_graph("/resultados/grafica-aceleracion", "grafica_aceleracion", "GraficarDatos_accel")
    _add_graph("/resultados/grafica-velocidad", "grafica_velocidad", "GraficarDatos_vel")
    _add_graph("/resultados/grafica-espacio", "grafica_espacio", "GraficarDatos_esp")

    @bp.get("/camera")
    def camera():
        manager = current_app.extensions["lease_manager"]
        epoch = manager.validate_stream(request.args.get("t"))

        def generate():
            reader = reader_factory()
            try:
                for frame in reader:
                    if not manager.is_current(epoch):
                        return
                    output = io.BytesIO()
                    Image.fromarray(frame).resize((400, 350)).save(output, format="WEBP")
                    yield (
                        b"--frame\r\nContent-Type: image/webp\r\n\r\n"
                        + output.getvalue()
                        + b"\r\n"
                    )
                    time.sleep(1 / frame_rate)
            finally:
                close = getattr(reader, "close", None)
                if close is not None:
                    close()

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return bp
