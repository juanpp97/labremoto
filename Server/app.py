import os
import tempfile
from datetime import timedelta

from decouple import Csv, config
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import create_access_token, JWTManager
from flask_sqlalchemy import SQLAlchemy

import LabRem as LR
from hardware.labrem_driver import LabRemDriver
from hardware.routes import create_hardware_blueprint
from lease.logging_config import configure_logging
from lease.settings import LeaseSettings
from lease.sql_history import build_sql_history
from lease.wiring import setup_resource

###################### Configuracion ######################
configure_logging(config("LOG_LEVEL", default="INFO"), config("LOG_FORMAT", default="json"))
lease_settings = LeaseSettings.from_env()

app = Flask(__name__)
# En producción frontend y API comparten dominio (proxy de Apache): CORS_ORIGINS puede
# restringirse o dejarse vacío. El default "*" mantiene el desarrollo local funcionando.
CORS(app, origins=config("CORS_ORIGINS", default="*", cast=Csv()))
app.config["JWT_SECRET_KEY"] = config("JWT_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=lease_settings.jwt_lifetime)
app.config['SQLALCHEMY_DATABASE_URI'] = config("DATABASE_URI")
jwt = JWTManager(app)

###################### Modelos ######################
db = SQLAlchemy(app)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user', server_default='user')

class TokenBlocklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    date_created = db.Column(db.DateTime, nullable=False)

# Historial de leases (tabla lease_history, ver migrations/001_lease.sql)
LeaseHistory, lease_history_store = build_sql_history(db, app)

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

###################### Login (identidad) ######################
# El JWT solo identifica al usuario. El acceso al hardware lo controla el lease:
# POST /resource/acquire (ver lease/flask_api.py).
@app.route("/", methods = ["POST"])
def index():
    username = request.json.get("username")
    user = User.query.filter_by(username=username).first()
    if user:
        return jsonify(token=create_access_token(identity=username))
    return (jsonify(msg = "Credenciales Incorrectas", code="E00"), 401)

###################### Lease + hardware ######################
def is_admin(identity):
    try:
        user = User.query.filter_by(username=identity).first()
    except Exception:
        app.logger.exception("No se pudo consultar el rol del usuario")
        return False
    return bool(user and user.role == "admin")

LR.conectar()
# El estado del lease vive en memoria: un solo proceso. LEASE_LOCK_FILE vacío desactiva el guard.
setup_resource(
    app, LabRemDriver(LR), lease_settings, is_admin=is_admin, history_store=lease_history_store,
    process_lock_path=config(
        "LEASE_LOCK_FILE", default=os.path.join(tempfile.gettempdir(), "labrem-lease.lock")
    ),
)
app.register_blueprint(create_hardware_blueprint(LR))

if __name__ == '__main__':
    app.run(host='10.150.0.102', port=80)
    # app.run(debug=True)
