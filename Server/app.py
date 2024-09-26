from flask import Flask, send_file, Response, jsonify, request
from flask_cors import CORS
from time import sleep
import imageio as iio
import io
from flask_cors import CORS
from PIL import Image
from flask_sqlalchemy import SQLAlchemy 
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, create_refresh_token, get_jwt_identity, get_jwt, verify_jwt_in_request, get_jti
from datetime import timedelta, datetime
import LabRem as LR
import threading

###################### Configuracion ######################
app = Flask(__name__)
CORS(app)
app.config["JWT_SECRET_KEY"] = 'hd-hd89756-3!45&fsd+g646%/1'
jwt = JWTManager(app)
expiration_minutes = 10

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=expiration_minutes)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(minutes=expiration_minutes + 10)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://lrfica:Gestion+-lrFICA!@10.150.0.101:3306/gestionUsuarios'

###################### Modelos ######################
db = SQLAlchemy(app)
class Usuarios(db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(40), nullable=False)
    password = db.Column(db.String(50), nullable=False)
    recovery_token = db.Column(db.String(255), nullable=True)
    token_expires = db.Column(db.DateTime, nullable=True)
    clase = db.Column(db.String(80), nullable=False, default="Usuario Estandar")
    email = db.Column(db.String(30), nullable=False, index=True)
    apellido = db.Column(db.String(25), nullable=False)
    verificado = db.Column(db.Boolean, nullable=False, default=False)
    id_sesion = db.Column(db.String(255), nullable=True)
    dni = db.Column(db.String(10), nullable=True)
    timestamp = db.Column(db.TIMESTAMP, nullable=False)
    clave_aleatoria = db.Column(db.String(10), nullable=True)

    
class TokenBlocklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    date_created = db.Column(db.DateTime, nullable=False)
    
LR.conectar()

###################### Variables Globales ######################
busy = False
time_stamp = None
frame_rate = 30
last_token = None
###################### Callbacks ######################
@jwt.unauthorized_loader
def callback(str):
    return (jsonify(msg="No tienes permiso para acceder a esta url", code="F00"), 401)

@jwt.expired_token_loader
def callback(jwt_header, jwt_payload):
    return (jsonify(msg="Ya no puedes acceder a esta url", code="F01"), 401)

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token = db.session.query(TokenBlocklist.id).filter_by(jti=jti).scalar()
    return token is not None

@jwt.invalid_token_loader
def callback(str):
    return (jsonify(msg = "Credenciales inválidas", code="F02"), 401)

def verificar_token(token):
    if last_token is None: return 0
    jti = token["jti"]
    if jti != last_token: return 0
    return 1

###################### Vistas ######################
@app.route('/verificar_token', methods = ['GET'])
@jwt_required()
def verificar():
    token = get_jwt()
    return jsonify(msg="Token válido") if verificar_token(token) else (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)

@app.route("/", methods = ["POST"])
def index():
    global busy, last_token, time_stamp

    if busy: 
        seconds_remaining = expiration_minutes*60 - (datetime.now() - time_stamp).total_seconds()
        return (jsonify(msg = f"Laboratorio ocupado. Tiempo restante {int(seconds_remaining/60)} minutos y {int(seconds_remaining % 60)} segundos"), 400)
    username = request.json.get("username")
    user = Usuarios.query.filter_by(username=username).first()
    access_token = None
    if user:
        access_token = create_access_token(identity=username)
        refresh_token = create_refresh_token(identity=username)
        busy = True
        time_stamp = datetime.now()
        timer_thread = threading.Thread(target=reset_flag)
        timer_thread.start()
        # return jsonify(token=access_token, distancia = LR.distancia)
        last_token = get_jti(access_token)
        return jsonify(token={"access": access_token, "refresh": refresh_token})
    return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)

def reset_flag():
    global busy
    sleep(expiration_minutes*60) 
    busy = False
    return

@app.route("/inclinar", methods = ["POST"])
@jwt_required()
def inclinar():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    if not LR.consultarEstado(): return (jsonify(msg =  "Error al enviar comando", code = "E01"), 400)
    
    angulo = request.form.get("angulo", 0)
    try:
        res = LR.enviarAnguloCin(angulo)
    except LR.AnguloInvalidoError as e: 
        return (jsonify(msg =  e, code="E02"), 400)
    except LR.TimeOutError as e: 
        return (jsonify(msg =  e, code="E03"), 504)
    
    return (jsonify(msg =  "Base Inclinada"), 200) if res else (jsonify(msg =  "Error al enviar comando"), 400)
        


@app.route("/iniciar", methods = ["GET"])
@jwt_required()
def iniciar():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    try:
        res = LR.iniExp()
    except LR.TimeOutError as e:
        return (jsonify(msg =  e, code ="E03"), 504)
    sleep(5)
    return jsonify(msg = "Experimento realizado con éxito") if res else (jsonify(msg = "Error al enviar comando", code="E01"), 400)
        
    
@app.route("/reiniciar", methods = ["GET"])
@jwt_required()
def reiniciar():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    try:
        res = LR.reinExp()
    except LR.TimeOutError as e:
        return (jsonify(msg =  e), 504)
    
    return jsonify(msg = "Reiniciado correctamente") if res else (jsonify(msg = "Ha ocurrido un error", code="E01"), 400)


@app.route('/grafica-sensores')
@jwt_required()
def datosRecibidos():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    output=LR.GraficarDatos()
    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-aceleracion')
@jwt_required()
def datosRecibidos_accel():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    output=LR.GraficarDatos_accel()    
    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-velocidad')
@jwt_required()
def datosRecibidos_vel():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    output=LR.GraficarDatos_vel()
    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-espacio')
@jwt_required()
def datosRecibidos_esp():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    output=LR.GraficarDatos_esp()
    return Response(output, mimetype='image/png')

# Camara
def generate():
    global camera
    while busy:
        for frame in iio.get_reader("<video0>"):
            resized_frame = Image.fromarray(frame).resize((400, 350))
            output = io.BytesIO()
            resized_frame.save(output, format='WEBP')
            frame_bytes = output.getvalue()
            yield (b'--frame\r\nContent-Type: image/webp\r\n\r\n' + frame_bytes + b'\r\n')
            sleep(1 / frame_rate)


@app.route('/camera')
def video():
    if busy:
        response = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    return jsonify(msg='Acceso denegado')
###################### Vistas Admin ######################

@app.route("/hard-reset", methods = ["GET"])
@jwt_required()
def hard_reset():
    global busy
    
    if not busy: return {}
    identity = get_jwt_identity()
    user = Usuarios.query.filter_by(username=identity).first()
    if user and user.clase == "Administrador":
        LR.hardReset()
    return {}

@app.route('/verificar_estado', methods = ['GET'])
@jwt_required()
def estado():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    identity = get_jwt_identity()
    user = Usuarios.query.filter_by(username=identity).first()
    if user and user.clase == "Administrador":
        return jsonify(msg=busy)
    return jsonify(msg = "Credenciales Incorrectas", code="E00"), 401


@app.route("/change-state", methods = ["GET"])
@jwt_required()
def change_state():
    global busy
    
    if not busy: return {}
    identity = get_jwt_identity()
    user = Usuarios.query.filter_by(username=identity).first()
    if user and user.clase == "Administrador":
        busy = False
        return jsonify(msg="Cambiado correctamente")
    return {}

if __name__ == '__main__':
    app.run(host='10.150.0.102', port=80)
    # app.run(debug=True)
    