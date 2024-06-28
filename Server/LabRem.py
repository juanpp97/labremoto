import paho.mqtt.client as mqtt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

# from matplotlib import pyplot as plt #Debug

from scipy.interpolate import lagrange
from numpy import linspace
import numpy as np

import base64
from io import BytesIO
from parse import parse
import time
import GlobalVars as GV
GV.initialize()

# Temas donde se realiza la comunicacion entre la raspi y los micros:
# topic_comandos_cin:       Para enviar comandos, se envian a los 2 micros
# topic_tiempo_cin:         Para recibir los tiempos de los sensores de barrera
# topic_tiempo_cin_movil:   Para recibir los datos del acelerometro
# topic_info:               Para recibir el estado de la base
topic_comandos_cin = "/labRem/cinematica/baseCom"
topic_tiempo_cin = "/labRem/cinematica/baseTiempo"
topic_tiempo_cin_movil = "/labRem/cinematica/movilDatos"
topic_info = "/labRem/cinematica/baseInfo"

#Variables para las graficas
n=0
Ang=0
N_SAMPLES=200
accelx=[0]*N_SAMPLES
accelz=[0]*N_SAMPLES
t_movil=[0]*N_SAMPLES


#distancia de los sensores respecto al 0 en m. se tiene que ver en la tabla. suerte
distancia=[0,0.02,0.30,0.60,0.90]

# Bloqueo de comandos
comBlock=False
estado_base=''

class AnguloInvalidoError(BaseException):
    pass

class TimeOutError(BaseException):
    pass

# on_connect callback:
# Cuando se conecta al servidor se subscribe a los temas donde se reciben datos.
# El segundo argumento es el QoS. Valores: 0, 1 o 2
def on_connect(client, userdata, flags, rc):
    client.subscribe(topic_tiempo_cin,0)
    client.subscribe(topic_tiempo_cin_movil,2)
    client.subscribe(topic_info,0)
    print("Connected to MQTT broker with result code "+str(rc))
    
# tiempoRecibidoCin:
# cuando llega el dato de los sensores de barrera los guarda en el vector GV.tiempo_c
# Este dato se recibe luego de que el riel toca el final de carrera
# Procesa los datos para las graficas
def tiempoRecibidoBase(client, userdata, message):
    ph=parse("b'{},{},{},{}'",str(message.payload))
    GV.tiempo_c=list(map(float, ph))
    procesarDatos()

# datoRecibidoMovil:
# Por cada dato recibido de la forma [ t, ax, az] lo guarda en un vector de tiempos, uno de 
# aceleracion en x y otro en z hasta que se recibieron un total de 200 puntos.
#       -La frecuencia de muestreo del acelerometro fue establecida en 100Hz, por lo que 200 puntos equivale a
#     1990ms. 
#       -El movil comienza el envio de los datos luego de 1990ms desde que se recibio el comando de 
#     iniciar experimento.
#       -El tiempo que demora el microcontrolador para el envio de cada dato es 10ms. Por lo que la totalidad
#     de los datos se reciben luego de ~4s de iniciado el experimento.
def datoRecibidoMovil(client, userdata, message):
    global n
    global t_movil
    global accelx
    global accelz
    ph=parse("b'{},{},{}'",str(message.payload))
    temp=list(map(float, ph))
    t_movil[n]=temp[0]
    accelx[n]=temp[1]
    accelz[n]=temp[2]
    n=n+1
    if (n>=200):
        n=0

# infoRecibida:
# Se usa para recibir el estado de la base. y lo guarda en una variable global
# Estados posibles:                                                     Listo para recibir comandos?
#       "Iniciando Exp..."      Cuando se suelta el movil               NO
#       "Exp Terminado"         Cuando se disparan los 4 sensores       NO
#       "Posicionando base"     Cuando se esta inclinando el riel       NO
#       "Base lista"            Cuando termina de inclinar la rampa     SI
#       "Reiniciando Exp"       Cuando la rampa esta volviendo a 0      NO
#       "Exp Reiniciado"        Cuando la rampa termina de volver a 0   SI
#       "ESPERANDO COMANDO   "  Cuando inicia el micro                  SI
def infoRecibida(client, userdata, message):
    global estado_base
    estado_base=parse("b'{}'",str(message.payload))[0]

    
# Configuracion del cliente MQTT
broker="10.42.0.1"
client = mqtt.Client()
client.on_connect = on_connect
client.message_callback_add(topic_tiempo_cin, tiempoRecibidoBase)
client.message_callback_add(topic_tiempo_cin_movil, datoRecibidoMovil)
client.message_callback_add(topic_info, infoRecibida)

# conectar:
# Funcion para conectarse al servidor MQTT.
# Es necesario ejecutarla una vez para poder enviar y recibir comandos
def conectar():
    client.connect(broker, 1883, 60)
    client.loop_start()

# enviarComandoBM:
# args:
#       topic: tema a donde enviar el mensaje
#       message: mensaje a enviar
#       timeout: tiempo maximo de espera en segundos
# Envia el comando en modo bloqueante solo si la base esta lista. Es recomendable usarlo para manejar la base
# devuelve 1 si el comando se envio y la base esta lista
# devuelve 0 si el comando no se envio porque la base no esta lista
# devuelve TimeOutError si se excedio el timeout.
def enviarComandoBM(topic,message,timeout,target=0):
    if not consultarEstado():
        return 0
    client.publish(topic, message)
    t0=time.time()
    t1=time.time
    while timeout>(t1()-t0):
        if consultarEstado(target):
            return 1
    return TimeOutError("Tiempo de espera agotado")

# consultarEstado:
# Esta funcion consulta el estado de la base.
# Devuelve True si la base esta lista para recibir comandos
# False de lo contrario
# Toma un argumento target, que indica el estado de la base que se espera. Por defecto espera cualquier estado de listo
def consultarEstado(target=0):
    client.publish(topic_comandos_cin,"com5")
    time.sleep(0.2)
    if target==0:
        if(estado_base=='Base lista' or estado_base=='Exp Reiniciado' or estado_base=="ESPERANDO COMANDO   "):
            return True
        else:
            return False
    else:
        if estado_base==target:
            return True
        else:
            return False

# enviarAnguloCin:
# Inclina el riel al angulo en grados pasado como parametro. Solo acepta valores entre 0 y 15
# devuelve 1 si esta listo, 0 si la base no esta lista para recibir comandos y -1 si se excedio el tiempo de espera
# Devuelve excepcion de angulo invalido en caso de que esté fuera de rango
def enviarAnguloCin(angulo):
    global Ang
    Ang=float(angulo)
    if Ang>15 or Ang<0:
        raise AnguloInvalidoError("Ángulo Inválido")
    return enviarComandoBM(topic_comandos_cin, "com3 ang {}".format(Ang), 10,target='Base lista')

# GraficarDatos:
# Toma los datos de la variable GV.tiempo_c y los grafica. Devuelve la grafica del espacio
# recorrido por el movil en funcion de los sensores de la base
def GraficarDatos():
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    axis.set_title("Sensores de barrera")
    axis.set_xlabel("Tiempo (ms)")
    axis.set_ylabel("Distancia(cm)")
        
    t=GV.tiempo_c.copy()
    t.insert(0,0)
    
    #interpolacion de los puntos leidos por los sensores
    interpolador= lagrange(t,distancia)
    t_int=linspace(0,t[4],100)
    esp_int=interpolador(t_int)
    
    axis.plot(t,distancia,'ro',label='Sensores')
    axis.plot(t_int,esp_int,label='Interpolación')

    axis.legend()
    # plt.plot(t,distancia,'ro')  #Debug
    # plt.plot(t_int,esp_int)     #Debug
    # plt.show()                  #Debug
    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    img=output.getvalue()
    yield img

# procesarDatosMovil:
# Procesa los datos de aceleracion provenientes del movil y genera los de velocidad
# y espacio recorrido.
# En el caso que no esten disponibles, utiliza los de la base, los deriva y obtiene la velocidad y aceleracion.
# Si esos no estan disponibles tiene un comportamiento indefinido
def procesarDatos():
    global acel_m,vel_m,esp_m,t_m,ind_max,t_movil
    t_max=np.sum(np.array(GV.tiempo_c))
    temp=[0]*len(GV.tiempo_c)
    temp[0]=GV.tiempo_c[0]
    for k in range(1,len(GV.tiempo_c)):
        temp[k]=GV.tiempo_c[k]+temp[k-1]
    GV.tiempo_c=temp.copy()
    try:
        ind_max=int(t_max/t_movil[-1]*N_SAMPLES)
        t_m = np.array(t_movil)
        acel_m = np.array(accelx)*0.00981 # m/s^2
        vel_m = np.zeros(np.size(acel_m)) # m/s
        esp_m = np.zeros(np.size(acel_m)) # m
        #integracion con la regla del trapecio para obtener vel y esp
        for k in range(1,np.size(acel_m)):
            dt = t_m[k] - t_m[k-1]
            vel_m[k] = vel_m[k-1] + 0.5 * ( acel_m[k-1] + acel_m[k] ) * dt
            esp_m[k] = esp_m[k-1] + 0.5 * ( vel_m[k-1] + vel_m[k] ) * dt
        # print('TodoOk')
    except:
        t_m = np.linspace(0,t_max,int(t_max/10)+1)
        ind_max=np.size(t_m)-1
        t=GV.tiempo_c.copy()
        t.insert(0,0)
        # print('Derivando')
        #interpolacion de los puntos leidos por los sensores
        interpolador= lagrange(t,distancia)
        esp_m=interpolador(t_m)
        Muestras=np.size(esp_m)
        vel_m=np.zeros(Muestras)
        acel_m=np.zeros(Muestras)
        for k in range(1,Muestras):
            dt=(t_m[k]-t_m[k-1])*0.001
            vel_m[k]=(esp_m[k]-esp_m[k-1])/dt
            acel_m[k]=(vel_m[k]-vel_m[k-1])/dt
        acel_m[0:2]=acel_m[3]
        t_movil=t_m

# GraficarDatos_accel:
# Grafica los datos de aceleracion con los datos recibidos del movil
# en el mismo rango temporal que los sensores de barrera. Esto se hace para evitar el ruido
# en la señal debido al golpe cuando el movil frena.
# Devuelve una imagen donde se encuentran graficados los valores de aceleracion promedio
# el teorico y el real
def GraficarDatos_accel():
    fig = Figure()
    global Ang
    global accelx
    axis = fig.add_subplot(1, 1, 1)
    axis.set_title("Aceleracion")
    axis.set_xlabel("Tiempo (ms)")
    axis.set_ylabel("Aceleracion (m/s^2)")
    
    prom=np.average(acel_m[0:ind_max])
    if Ang !=0:
        seno=np.sin(Ang*np.pi/180)*9.81
    
    axis.plot(t_movil[0:ind_max],acel_m[0:ind_max])
    axis.plot([t_movil[0],t_movil[ind_max]],[seno,seno])
    axis.plot([t_movil[0],t_movil[ind_max]],[prom,prom])
    axis.legend(['Acelerometro','Teorico','Promedio'])
    
    # plt.plot(t_movil[0:ind_max],acel_m[0:ind_max],label='Orig')          #Debug
    # plt.plot([t_movil[0],t_movil[ind_max]],[seno,seno],label='seno')     #Debug
    # plt.plot([t_movil[0],t_movil[ind_max]],[prom,prom],label='Promedio') #Debug
    # plt.legend()                                                         #Debug
    # plt.show()                                                           #Debug
    
    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    img=output.getvalue()
    yield img    

# GraficarDatos_vel:
# Esta funcion devuelve el grafico de la velocidad en el mismo rango temporal
# que los sensores de barrera
def GraficarDatos_vel():
    fig = Figure()
    
    axis = fig.add_subplot(1, 1, 1)
    axis.set_title("Velocidad")
    axis.set_xlabel("Tiempo (ms)")
    axis.set_ylabel("Velocidad(m/s)")
    
    #axis.set_yticklabels([])
    axis.plot(t_movil[0:ind_max],vel_m[0:ind_max])
    
    # plt.plot(t_movil[0:ind_max],vel_m[0:ind_max])   #Debug
    # plt.show()                                      #Debug
    
    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    img=output.getvalue()
    yield img

# GraficarDatos_esp:
# Esta funcion devuelve el grafico de la posicion recorrida en el mismo rango temporal
# que los sensores de barrera
def GraficarDatos_esp():
    fig = Figure()
    
    axis = fig.add_subplot(1, 1, 1)
    axis.set_title("Espacio Recorrido")
    axis.set_xlabel("Tiempo (ms)")
    axis.set_ylabel("Espacio (m)")
    
    #axis.set_yticklabels([])
    axis.plot(t_movil[0:ind_max],esp_m[0:ind_max])
    
    # plt.plot(t_movil[0:ind_max],esp_m[0:ind_max])   #Debug
    # plt.show()                                      #Debug
    
    output = BytesIO()
    FigureCanvas(fig).print_png(output)
    img=output.getvalue()
    yield img  

# iniExp:
# Esta funcion es la que se encarga de iniciar el ensayo, soltando el movil
# y luego reiniciando la base a 0 para realizar otro ensayo. Se ejecuta en modo
# bloqueante y devuelve lo mismo que enviarComandoBM
def iniExp():
    return enviarComandoBM(topic_comandos_cin,"com1",10)
    
# reinExp:
# Esta funcion reinicia la base para realizar otro ensayo. Es redundante ya que 
# cuando se inicia un ensayo la base vuelve a 0. Pero se puede utilizar si el movil
# no regreso al origen.
# Se ejecuta en modo bloqueante y devuelve lo mismo que enviarComandoBM
def reinExp():
    return enviarComandoBM(topic_comandos_cin,"com4",10)

# hardReset
# Realiza el reinicio completo de los microcontroladores
def hardReset():
    client.publish(topic_comandos_cin,"com6")

#Comandos posibles:
# com0      ->  noop
# com1      ->  Iniciar experimento, lo reinicia, envia la telemetria
# com2      ->  Enviar telemetria
# com3 ang  ->  Inclinar rampa a ang grados
# com4      ->  Reinicia el experimento
# com5      ->  Consulta el estado del micro
# com6      ->  Resetea los micros
# com7      ->  Pone el movil en deepSleep. 
               #Despues no se como sacarlo de ahi. asi que es equivalente a apagarlo para ahorrar bateria