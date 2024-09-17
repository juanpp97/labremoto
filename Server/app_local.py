from flask import Flask, send_file, Response, jsonify, request
from flask_cors import CORS
from time import sleep
import imageio as iio
import io
from flask_cors import CORS
from PIL import Image
from flask_sqlalchemy import SQLAlchemy 
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, create_refresh_token, get_jwt_identity, get_jwt, verify_jwt_in_request, get_jti
from datetime import timedelta
# import LabRem as LR

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from io import BytesIO
import threading


###################### Configuracion ######################
app = Flask(__name__)
CORS(app)
app.config["JWT_SECRET_KEY"] = "hd-hd89756-3!45&fsd+g646%/1"
jwt = JWTManager(app)
expiration_minutes = 2

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=expiration_minutes)
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://lrfica:Gestion+-lrFICA!@10.101.10.177:3306/LRFICA'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:juanp1997@localhost:3306/proyecto'

###################### Modelos ######################
db = SQLAlchemy(app)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    
class TokenBlocklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    date_created = db.Column(db.DateTime, nullable=False)

with app.app_context():
    db.create_all()
# LR.conectar()

###################### Variables Globales ######################
busy = False
frame_rate = 30
last_token = None
###################### Callbacks ######################
@jwt.unauthorized_loader
def callback(str):
    return (jsonify(msg="No tienes permiso para acceder a esta url"), 401)

@jwt.expired_token_loader
def callback(jwt_header, jwt_payload):
    return (jsonify(msg="Ya no puedes acceder a esta url"), 401)

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token = db.session.query(TokenBlocklist.id).filter_by(jti=jti).scalar()
    return token is not None

@jwt.invalid_token_loader
def callback(str):
    return (jsonify(err = "Credenciales inválidas"), 401)


def verificar_token(token):
    if last_token is None: return 0
    jti = token["jti"]
    if jti != last_token: return 0
    return 1

###################### Vistas ######################

@app.route('/verificar_flag', methods = ['GET'])
def flag():
    return jsonify(flag=busy)


@app.route('/verificar_token', methods = ['GET'])
@jwt_required()
def verificar():
    token = get_jwt()
    return jsonify(msg="Token válido") if verificar_token(token) else (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)

def reset_flag():
    global busy
    sleep(expiration_minutes*60) 
    busy = False

@app.route("/", methods = ["POST"])
def index():
    global busy, last_token
    if busy: return (jsonify(msg = "Laboratorio ocupado"), 400)
    username = request.json.get("username")
    # user = User.query.filter_by(username=username).first()

    access_token = None
    if username:
        access_token = create_access_token(identity="40722571")
        busy = True
        timer_thread = threading.Thread(target=reset_flag)
        timer_thread.start()
        # return jsonify(token=access_token, distancia = LR.distancia)
        last_token = get_jti(access_token)
        return jsonify(token=access_token)
    return jsonify(msg = "Credenciales Incorrectas"), 401


@app.route("/inclinar", methods = ["POST"])
@jwt_required()
def inclinar():
    # if not LR.consultarEstado(): return (jsonify(msg =  "Error al enviar comando"), 400)
    
    # angulo = request.form.get("angulo", 0)
    # try:
    #     res = LR.enviarAnguloCin(angulo)
    # except LR.AnguloInvalidoError as e: 
    #     return (jsonify(msg =  e), 400)
    # except LR.TimeOutError as e: 
    #     return (jsonify(msg =  e), 504)
    
    # return (jsonify(msg =  "Base Inclinada"), 200) if res else (jsonify(msg =  "Error al enviar comando"), 400)
    
    ##########################################################
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)

    success = True
    print("Inclinando la rampa")
    
    sleep(3)
    print("Inclinada")
    
    return jsonify(msg = "Rampa Inclinada correctamente") if success else (jsonify(msg = "Se ha producido un error"), 400)

@app.route("/iniciar", methods = ["GET"])
@jwt_required()
def iniciar():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # try:
    #     res = LR.iniExp()
    # except LR.TimeOutError as e:
    #     return (jsonify(msg =  e), 504)
    
    # return jsonify(msg = "Experimento realizado con éxito") if res else (jsonify(msg = "Error al enviar comando"), 400)
    
    ##########################################################
    
    success = True
    print("Iniciando experimento")
    sleep(5)
    print("Experimento iniciado")
    
    return jsonify(msg = "Experimento finalizado correctamente") if success else (jsonify(msg = "Se ha producido un error"), 400)

@app.route("/reiniciar", methods = ["GET"])
@jwt_required()
def reiniciar():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # try:
    #     res = LR.reinExp()
    # except LR.TimeOutError as e:
    #     return (jsonify(msg =  e), 504)
    
    # return jsonify(msg = "Reiniciado correctamente") if res else (jsonify(msg = "Ha ocurrido un error"), 400)
    
    ##########################################################
    
    success = True
    print("Reiniciando experimento")
    sleep(5)
    print("Experimento Reiniciando")
    
    return jsonify(msg = "Experimento reiniciado correctamente") if success else (jsonify(msg = "Se ha producido un error"), 400)
    
def graficar():
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)

    t_movil = np.linspace(0, 10, 100)  
    accelx = np.linspace(0, 1, 100)  
    axis.plot(t_movil, accelx)

    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    img = output.getvalue()
    yield img


@app.route('/grafica-sensores')
@jwt_required()
def datosRecibidos():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # output=LR.GraficarDatos()
    output = graficar()
    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-aceleracion')
@jwt_required()
def datosRecibidos_accel():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # output=LR.GraficarDatos_accel()
    output = graficar()
    
    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-velocidad')
@jwt_required()
def datosRecibidos_vel():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # output=LR.GraficarDatos_vel()
    output = graficar()

    return Response(output, mimetype='image/png')

@app.route('/resultados/grafica-espacio')
@jwt_required()
def datosRecibidos_esp():
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    # output=LR.GraficarDatos_esp()
    output = graficar()
    busy = False
    return Response(output, mimetype='image/png')

# Camara
def generate():
    global camera
    for frame in iio.get_reader("<video0>"):
        if not busy:
            return
        resized_frame = Image.fromarray(frame).resize((400, 350))
        output = io.BytesIO()
        resized_frame.save(output, format='WEBP')
        frame_bytes = output.getvalue()
        yield (b'--frame\r\nContent-Type: image/webp\r\n\r\n' + frame_bytes + b'\r\n')
        sleep(1/frame_rate) 

@app.route('/camera')
def video():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame') if busy else jsonify(msg = 'Acceso denegado')

###################### Vistas Admin ######################

@app.route("/hard-reset", methods = ["GET"])
@jwt_required()
def hard_reset():
    global busy
    
    if not busy: return {}
    identity = get_jwt_identity()
    user = User.query.filter_by(username=identity).first()
    if user and user == "admin":
        # LR.hardReset()
        pass
    return {}

@app.route("/change-state", methods = ["GET"])
@jwt_required()
def change_state():
    global busy
    token = get_jwt()
    if not verificar_token(token): return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)
    if not busy: return {}
    identity = get_jwt_identity()
    user = User.query.filter_by(username=identity).first()
    if user and user == "admin":
        busy = False
        return jsonify(msg="Cambiado correctamente")
    return {}

if __name__ == '__main__':
    #app.run(host='')
    app.run('127.0.0.1', port=5000)
    