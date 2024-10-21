from flask import Flask, send_file, Response, jsonify, request

from flask_sqlalchemy import SQLAlchemy 


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://lrfica:Gestion+-lrFICA!@10.150.0.101:3306/gestionUsuarios'


db = SQLAlchemy(app)

    
class TokenBlocklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    date_created = db.Column(db.DateTime, nullable=False)


with app.app_context():
    db.create_all()
if __name__ == '__main__':
    app.run('127.0.0.1', port=5000)
    