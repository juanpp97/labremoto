let lastCanvas;
const baseURL = 'https://labremotos.fica.unsl.edu.ar/raspi'
//const baseURL = 'http://127.0.0.1:5000/'
const container = document.querySelector('main.content')
const contentComponent = `
<section class="prediction">
<h2>Antes de comenzar el experimento, predice los resultados del mismo a partir de los siguientes videos
</h2>
<article class="video">
    <video src="static/video_normal.mp4" fullscreen autoplay controls></video>
    <video src="static/video_lento.mp4" fullscreen autoplay controls></video>

</article>
<div class="buttons">
    <button id="next">Estoy listo para predecir!</button>
</div>
<article class="pred_graphs">
    <p><strong>Atajos del teclado: </strong> Presiona <code>B</code> para borrar en la última gráfica utilizada o <code>Ctrl + Z</code> para deshacer el último trazo</p>
    <div class="canvas">
        <canvas id="canvasPos" height="300" width="350"></canvas>
        <canvas id="canvasVel" height="300" width="350"></canvas>
        <canvas id="canvasAc" height="300" width="350"></canvas>
    </div>
    <div class="buttons">
        <button id="save">Guardar predicciones</button>
    </div>                </article>
</section>
`
const alertComponent = (msg, cls) => `<div class="alert alert-dismissible text-center ${cls}">
<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
<p id="error-msg">${msg}</p>
</div>`
const experimento = '/experimento.html'
class PredictionCanvas {
    constructor(element, color, magnitude, points = []) {
        this.element = element;
        this.marginWidth = 20;
        this.element.width += this.marginWidth;
        this.ctx = this.element.getContext('2d');

        this.color = color;
        this.magnitude = magnitude;
        this.points = points;
        this.gridWidth = (this.element.width - this.marginWidth) / 6;
        this.gridHeight = this.element.height / 7;
        this.element.addEventListener("click", (event) => this.getCoordinates(event));
        this.drawAxis();

    }

    draw(x, y, lastPoint) {
        this.ctx.beginPath();
        this.ctx.fillStyle = this.color;
        this.ctx.strokeStyle = this.color;
        this.ctx.beginPath();
        this.ctx.arc(x, y, 2, 0, Math.PI * 2);
        this.ctx.fill();

        if (!this.points.length || !lastPoint) {
            this.ctx.moveTo(x, y);
            return;
        }

        /* Dibujo la linea entre los ultimos puntos */
        this.ctx.beginPath();
        this.ctx.lineWidth = 2;
        this.ctx.moveTo(lastPoint.x, lastPoint.y);
        this.ctx.lineTo(x, y);
        this.ctx.stroke();
    }
    drawNumber(num, posX, posY) {
        this.ctx.font = "13px sans-serif";
        this.ctx.fillStyle = "black";
        const text = num == 1
            ? num.toFixed(0).toString()
            : num.toFixed(1).toString();
        this.ctx.textAlign = 'left';
        this.ctx.fillText(text, posX, posY);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    drawAxis() {

        this.ctx.clearRect(0, 0, this.element.width, this.element.height);
        this.ctx.fillStyle = "#fff";
        this.ctx.fillRect(0, 0, this.element.width, this.element.height);
        this.ctx.strokeStyle = '#eee';
        this.ctx.lineWidth = 1.5;
        this.ctx.beginPath();

        let axis = 0;
        for (let x = this.gridWidth; x <= this.element.width - this.marginWidth; x += this.gridWidth) {
            this.ctx.moveTo(x, this.gridHeight);
            this.ctx.lineTo(x, this.element.height - this.gridHeight);
            if (axis == 0) {
                this.drawNumber(axis, this.gridWidth - 25, this.element.height - 30);
            } else {
                this.drawNumber(axis, x - 8, this.element.height - 25);
            }
            axis += 0.2;
        }

        axis = 0;
        for (let y = this.element.height - this.gridHeight; y >= this.gridHeight; y -= this.gridHeight) {
            this.ctx.moveTo(this.gridWidth, y);
            this.ctx.lineTo(this.element.width - this.marginWidth, y);
            if (axis != 0) {
                if (axis == 1) {
                    this.drawNumber(axis, this.gridWidth - 15, y + 5);
                } else {
                    this.drawNumber(axis, this.gridWidth - 25, y + 5);
                }
            }
            axis += 0.2;
        }

        this.ctx.stroke();
        this.ctx.font = "bold 15px sans-serif";
        this.ctx.fillText("Tiempo", (this.element.width - this.marginWidth) / 2, this.element.height - 5);

        this.ctx.font = "bold 17px sans-serif";
        this.ctx.textAlign = 'center';
        this.ctx.translate(20, this.element.height / 2);
        this.ctx.rotate(-Math.PI / 2);
        this.ctx.fillText(this.magnitude, 0, 0);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);

        this.ctx.font = "bold 20px sans-serif";
        this.ctx.textAlign = 'center';
        const title = "Predicción: " + this.magnitude;
        this.ctx.translate((this.element.width - this.marginWidth + this.gridWidth) / 2, this.gridHeight / 2);
        this.ctx.fillText(title, 0, 0);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        if (this.points.length > 1) {
            this.points.forEach((point, index) => {
                const lastPoint = index == 0 ? undefined : this.points[index - 1];
                this.draw(point.x, point.y, lastPoint);
            });
        }
    }
    getCoordinates(event) {
        lastCanvas = this;
        const rect = this.element.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        //Que no se pueda dibujar en la zona de los ejes
        if (x < this.gridWidth || y > this.element.height - this.gridHeight || y < this.gridHeight || x > this.element.width - this.marginWidth) return;

        const lastPoint = this.points.at(-1);
        this.draw(x, y, lastPoint);
        this.points.push({ x, y });
    }

    undoLastPoint() {
        if (this.points.length > 0) {
            this.points.pop();
            this.ctx.clearRect(0, 0, this.element.width, this.element.height);
            this.drawAxis();

            this.points.forEach((point, index) => {
                const lastPoint = index == 0 ? undefined : this.points[index - 1];
                this.draw(point.x, point.y, lastPoint);
            });
        }
    }

    deleteCanvas() {
        this.ctx.clearRect(0, 0, this.element.width, this.element.height);
        this.points = [];
        this.drawAxis();
    }
    toHTML() {
        const url = this.element.toDataURL();
        return `<a download="Prediccion_${this.magnitude.toLowerCase()}.jpg" href="${url}" title="${this.magnitude}">
                            <img alt="${this.magnitude}" src="${url}">
                        </a>`
    }
    toURL() {
        return this.element.toDataURL();
    }

}

async function handleExperiment(event) {
    const spinner = document.getElementById('spinner');
    try {
        event.target.hidden = true;
        spinner.hidden = false;

        const token = JSON.parse(localStorage.getItem('token')) ?? '';
        const auth = await fetch(baseURL + '/verificar_token', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer ' + JSON.parse(localStorage.getItem('token')) ?? ''
            }
        })
        if(auth.ok){
            location.href = 'experimento.html'
            return
        }else{
            event.target.hidden = false;
            spinner.hidden = true;
        }
        
        const res = await fetch(baseURL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                "username": "40722571",
            })
        })
        const data = await res.json();
        if (!res.ok) {
            event.target.hidden = false;
            spinner.hidden = true;
            if (res.status == 401) throw new PermissionError("Credenciales Incorrectas")
            if (res.status == 400) throw new StatusError(data.msg)
        }
        localStorage.setItem('token', JSON.stringify(data.token))
        location.href = 'experimento.html'
    } catch (error) {
        window.scrollTo(0, 0)
        if (error.name === 'PermissionError') {
            container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
            return
        }
        if (error.name === 'StatusError') {
            container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
            return
        }
        container.insertAdjacentHTML('afterbegin', alertComponent('Laboratorio no disponible', 'alert-danger'))

        // location.href = '/'
    }
}

function iniciarCanvas(points = undefined) {
    const canvasVel = new PredictionCanvas(document.getElementById('canvasVel'), 'green', 'Velocidad', points?.velocidad);
    const canvasAc = new PredictionCanvas(document.getElementById('canvasAc'), 'blue', 'Aceleración', points?.aceleracion);
    const canvasPos = new PredictionCanvas(document.getElementById('canvasPos'), 'red', 'Posición', points?.posicion);
    /* ------------- Borrar o deshacer en las gráficas ------------- */
    function handleDelete(event) {
        if (event.ctrlKey && ['z', 'Z'].includes(event.key)) lastCanvas.undoLastPoint();
        if (['b', 'B'].includes(event.key)) lastCanvas.deleteCanvas();

    }
    document.addEventListener('keydown', handleDelete);

    const next = document.getElementById('next');
    next?.addEventListener('click', () => {
        next.remove();
        const predGraphs = document.querySelector('.pred_graphs');
        predGraphs.style.height = '500px';
        setTimeout(() => {
            predGraphs.style.height = 'auto';
        }, 300);
    });


    /* ------------- Al presionar save ------------- */
    document.getElementById('save')?.addEventListener('click', (event) => {

        document.removeEventListener('keydown', handleDelete);
        localStorage.setItem('lastPred', JSON.stringify({
            posicion: canvasPos.toURL(),
            velocidad: canvasVel.toURL(),
            aceleracion: canvasAc.toURL(),
        }));
        localStorage.setItem('points', JSON.stringify({
            posicion: canvasPos.points,
            velocidad: canvasVel.points,
            aceleracion: canvasAc.points,
        }));
        const innerDiv = canvasPos.toHTML() + canvasVel.toHTML() + canvasAc.toHTML();
        container.style.transition = '';
        container.style.opacity = 0;
        /* -------------------- Mostrar los resultados --------------------*/

        container.innerHTML = `
                            <button id="return"> <img src="static/return.svg"></button>
                            <section id="results">
                            <h2> Resultados de la predicción </h2>
                            <div class="canvas"> ${innerDiv} </div>
                            <div class="buttons">
                            <button id="download"> Descargar las predicciones </button>
                            <button id="init"> Iniciar experimento </button>
                            <div class="spinner-border" id="spinner" hidden></div>
                            </div>                            
                            </section>
                            `;
        container.style.transition = 'opacity 300ms ease';
        container.style.opacity = 1;
        document.getElementById('init').addEventListener('click', handleExperiment);
        document.getElementById('return')?.addEventListener('click', () => {
            container.style.transition = '';
            container.style.opacity = 0;
            /* -------------------- Cuando queres cambiar las predicciones --------------------*/

            container.innerHTML = `
            <section class="prediction">
                <article class="pred_graphs" style="height: auto">
                    <div class="canvas">
                        <canvas id="canvasPos" height="300" width="350"></canvas>
                        <canvas id="canvasVel" height="300" width="350"></canvas>
                        <canvas id="canvasAc" height="300" width="350"></canvas>
                    </div>
                    <div class="buttons"> 
                    <button id="save"> Guardar predicciones </button>

                    </div>
                    </article>
            </section>
            `
            container.style.transition = 'opacity 300ms ease';
            container.style.opacity = 1;
            return iniciarCanvas(JSON.parse(localStorage.getItem("points")))
        })
        document.getElementById('download')?.addEventListener('click', handleDownload);


    });
}

function handleDownload() {
    const links = document.querySelectorAll('#results a');

    for (link of links) link.click();
}

function manageLoad() {
    const prediction = contentComponent;
    /* ------------- Si hay una prediccion previa, la muestra en vez de la seccion de prediccion ------------- */
    if (typeof localStorage !== "undefined" && localStorage.getItem("lastPred")) {
        /*
        lastPred = {
            posicion: url,
            velocidad; url,
            aceleracion: url,
        }
        */
        let innerDiv = "";
        let lastPred = JSON.parse(localStorage.getItem("lastPred"));
        for (const magnitude in lastPred) {
            innerDiv += ` 
            <a download="Prediccion_${magnitude}.jpg" href="${lastPred[magnitude]}" title="${magnitude}">
                <img alt="${magnitude}" src="${lastPred[magnitude]}">
            </a>`
        }
        let expDiv = '';
        if (localStorage.getItem("lastExp") ?? false) {
            const lastExp = JSON.parse(localStorage.getItem("lastExp"));
            for (const magnitude in lastExp) {
                expDiv += ` 
                <a download="Experimento_${magnitude}.jpg" href="${lastExp[magnitude]}" title="Experimento_${magnitude}">
                    <img alt="Experimento_${magnitude}" src="${lastExp[magnitude]}">
                </a>`
            }
        }
        /* -------------------- Cuando hay predicciones guardadas --------------------*/
        container.innerHTML = `
        <h2> Tus últimas predicciones:</h2>
        <section id="results">
        <div class="canvas"> ${innerDiv} </div>
        ${expDiv ? `
        <h2> Tus últimas graficas experimentales:</h2>

        <div class="canvas"> ${expDiv} </div>` : ''}

        <div class="buttons">
        <button id="predict"> Hacer otra predicción </button>
        <button id="download"> Descargar las graficas </button>
        <button id="init"> Iniciar experimento </button>
        <div class="spinner-border" id="spinner" hidden></div>

        </div>
        </section>
        `
        document.getElementById('init').addEventListener('click', handleExperiment);
        document.getElementById('download')?.addEventListener('click', handleDownload);
        document.getElementById('predict')?.addEventListener('click', () => {
            container.style.opacity = 0;
            container.innerHTML = prediction;
            container.style.transition = 'opacity 300ms ease';
            container.style.opacity = 1
            iniciarCanvas();
        });
        return
    } else {
        container.innerHTML = contentComponent;
        iniciarCanvas();
        return;
    }

}

window.addEventListener('load', manageLoad);