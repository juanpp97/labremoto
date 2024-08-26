/*
TO DO: 
- Add timer showing remaining time
*/

class PermissionError extends Error {
    constructor(message) {
        super(message);
        this.name = 'PermissionError';
    }
}
class StatusError extends Error {
    constructor(message) {
        super(message);
        this.name = 'StatusError';
    }
}
class GraphError extends Error {
    constructor(message) {
        super(message);
        this.name = 'GraphError';
    }
}
const baseURL = 'https://labremotos.fica.unsl.edu.ar/raspi'
//const baseURL = 'http://127.0.0.1:5000/'
let interval;
const container = document.querySelector('main.content')
const errorMessage = document.getElementById('error-msg')
const alertDiv = document.querySelector('.alert')
const mainComponent = `
<section class="experimento"> 
<article class="principal">
<div class="item">

    <img src="" alt="Vista en vivo" id="frame">
</div>
<div class="item">
    <img src="" alt="Sensores de barrera" class="grafico" id="sensores">
</div>

</article>
<article class="form">
<form id="form-angulo">
    <label for="angulo">Ingrese el ángulo de inclinación de la rampa: </label>
    <input type="number" name="angulo" id="angulo" value="0" min="0" max="15">
    <button type="submit" id="inclinar"> Inclinar Rampa </button>
</form>
<button id="iniciar"> Iniciar Experimento </button>
<button type="submit" id="reiniciar"> Reiniciar Experimento </button>
<div class="spinner-border" id="spinner" hidden></div>

</article>
</section>
`

const resultComponent = (url, name) => `<a download="${name}.png" href="${url}" title="${name}">
<img alt="${name}" src="${url}" id="${name}">
</a>`
const alertComponent = (msg, cls) => `<div class="alert alert-dismissible text-center ${cls}">
<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
<p id="error-msg">${msg}</p>
</div>`
let requestPending = false
let spinner, inclinar, reiniciar, iniciar;
let lastAngle = 0;


async function getGraph(url){
    const res = await fetch(baseURL  + url, {
        method: 'GET',
        headers: {
            'Authorization': 'Bearer '+ JSON.parse(localStorage.getItem('token')) ?? ''
        }
    })
    const blob = await res.blob();
    if(!res.ok) throw new GraphError("Error al obtener la gráfica")
    return new Promise((resolve, _) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
}

async function sendAngle(event){
    event.preventDefault();
    if(requestPending) return
    const angle = document.getElementById('angulo');
    
    if(angle.value < 0 || angle.value > 15){
        angle.border = '1px solid #F00'
    }
    const formData = new FormData()
    formData.append("angulo", angle.value);
    try{
        requestPending = true;
        event.target.hidden = true;
        spinner.hidden = false;
        const res = await fetch(baseURL + '/inclinar', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer '+ JSON.parse(localStorage.getItem('token')) ?? ''
            },
            body: formData
        })

        if(!res.ok){
            requestPending = false;
            event.target.hidden = false;
            spinner.hidden = true;
            container.insertAdjacentHTML('afterbegin', alertComponent("Error al enviar angulo", 'alert-danger'))

            if(res.status == 401) throw new PermissionError("Ya no tienes permiso para ejecutar el laboratorio aqui")
            throw new StatusError(data.msg)
        }

        const data = await res.json();
        lastAngle = angle.value;
        requestPending = false;
        event.target.hidden = false;
        spinner.hidden = true;
        container.insertAdjacentHTML('afterbegin', alertComponent(data.msg, 'alert-success'))

    }catch(error){
        if(error.name === 'PermissionError'){
            document.getElementById('frame').src = '';
            document.querySelector('.experimento').innerHTML = `<a href="/LR-fisica/" id="return"> <img src="static/return.svg"></a>
            <h1 class="text-center"> ${error.message} </h1>
            `
            return
        }
        if(error.name === 'StatusError'){
            container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
            return
        }
    
    }
   

}

async function startExp(event){
    if(requestPending) return
    try{
        requestPending = true;
        event.target.hidden = true;
        spinner.hidden = false;
        const res = await fetch(baseURL + '/iniciar', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer '+ JSON.parse(localStorage.getItem('token')) ?? ''
            },
        })
        if(!res.ok){
            requestPending = false;
            event.target.hidden = false;
            spinner.hidden = true;
            container.insertAdjacentHTML('afterbegin', alertComponent("Error al iniciar experimento", 'alert-danger'))

            if(res.status == 401) throw new PermissionError("Ya no tienes permiso para ejecutar el laboratorio aqui")
            throw new StatusError(data.msg)
        }
        const data = await res.json();
        requestPending = false;
        event.target.hidden = false;
        spinner.hidden = true;
        container.insertAdjacentHTML('afterbegin', alertComponent(data.msg, 'alert-success'))

    }catch(error){
        if(error.name === 'PermissionError'){
            document.getElementById('frame').src = '';
            document.querySelector('.experimento').innerHTML = `<a href="/LR-fisica/" id="return"> <img src="static/return.svg"></a>
            <h1 class="text-center"> ${error.message} </h1>
            `
            return
        }
        if(error.name === 'StatusError'){
            container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
            return
        }
        return
    }
    let acGraph, velGraph, posGraph;
    try{
        acGraph = await getGraph('/resultados/grafica-aceleracion');
        velGraph = await getGraph('/resultados/grafica-velocidad');
        posGraph = await getGraph('/resultados/grafica-espacio');

    }catch(error){
        container.insertAdjacentHTML('afterbegin', alertComponent("Error al obtener las graficas", 'alert-danger'))
        return
    }
    
    localStorage.setItem('lastExp', JSON.stringify({
        aceleracion: acGraph,
        velocidad: velGraph,
        posicion: posGraph
    }))
    const sensors = document.getElementById('sensores')
    try{
        const res = await getGraph('/grafica-sensores')
        sensors.src = res
    }catch(error){
        sensors.hidden = true;
        console.log(error.message)
    }
    const result = `
    <section id="results">
    <h2> Resultados del experimento </h2>
        <div class="canvas"> 
        ${resultComponent(posGraph, 'posicion')}
        ${resultComponent(velGraph, 'velocidad')}
        ${resultComponent(acGraph, 'aceleracion')}
        </div>
    </section>
    `
    const resultElement = document.getElementById('results')
    if(!resultElement){
        container.insertAdjacentHTML('beforeend', `<hr> ${result}`)
    }else{
        result.innerHTML = result;
    }    


}

async function restartExp(event){
    if(requestPending) return
    try{
        requestPending = true;
        event.target.hidden = true;
        spinner.hidden = false;
        const res = await fetch(baseURL + '/reiniciar', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer '+ JSON.parse(localStorage.getItem('token')) ?? ''
            },
        })
        if(!res.ok){
            requestPending = false;
            event.target.hidden = false;
            spinner.hidden = true;
            container.insertAdjacentHTML('afterbegin', alertComponent("Error al reiniciar experimento", 'alert-danger'))
            if(res.status == 401) throw new PermissionError("Ya no tienes permiso para ejecutar el laboratorio aqui")
            throw new StatusError(data.msg)
        }
        const data = await res.json();
        requestPending = false;
        event.target.hidden = false;
        spinner.hidden = true;
        container.insertAdjacentHTML('afterbegin', alertComponent(data.msg, 'alert-success'))

    }catch(error){
        if(error.name === 'PermissionError'){
            document.getElementById('frame').src = '';
            document.querySelector('.experimento').innerHTML = `<a href="/LR-fisica/" id="return"> <img src="static/return.svg"></a>
            <h1 class="text-center"> ${error.message} </h1>
            `
            return
        }
        if(error.name === 'StatusError'){
            container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
            return
        }
    
    }
}

async function initComponent(){
    try {
        const res = await fetch(baseURL + '/verificar_token', {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer '+ JSON.parse(localStorage.getItem('token')) ?? ''
            },
        })
        if(!res.ok) throw new Error('No tienes suficientes permisos')
    } catch (error) {
        let expDiv = '';
        if(localStorage.getItem("lastExp") ?? false){
            const lastExp = JSON.parse(localStorage.getItem("lastExp"));
            for(const magnitude in lastExp){
                expDiv += ` 
                <a download="Experimento_${magnitude}.jpg" href="${lastExp[magnitude]}" title="Experimento_${magnitude}">
                    <img alt="Experimento_${magnitude}" src="${lastExp[magnitude]}">
                </a>`
            }
        }else{
            expDiv = '<h4 class="text-center"> No hay graficas para mostrar </h4>'
        }
        const result = `
        <a href="/" id="return"> <img src="static/return.svg"></a>
        <h2> Tus últimas graficas experimentales:</h2>
        <section id="results">
            <div class="canvas"> 
                ${expDiv}
            </div>
        </section>
        `
        container.innerHTML = result;
        return
    }
    container.innerHTML = mainComponent
    spinner = document.getElementById('spinner')
    reiniciar = document.getElementById('reiniciar')
    iniciar = document.getElementById('iniciar')
    inclinar = document.getElementById('inclinar')

    document.getElementById('frame').src = baseURL + '/camera'

    inclinar.addEventListener('click', sendAngle)
    iniciar.addEventListener('click', startExp)
    reiniciar.addEventListener('click', restartExp)

}

// async function handleLoad(){
//     try{
//         const res = await fetch(baseURL, {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json',
//             },
//             body: JSON.stringify({
//                 "username": "40722571", 
//             })
//         })
//         console.log(res)
//         const data = await res.json();
//         console.log(`Data:`)
//         console.log(data)
        

//         if(!res.ok){
//             if(res.status == 401) throw new PermissionError("No tienes permiso para acceder aqui")
//             if(res.status == 400) throw new StatusError(data.msg)
//         }
//         localStorage.setItem('token', JSON.stringify(data.token))
//         container.innerHTML = mainComponent
//         initComponent();
//     }catch(error){
//         console.log(error)
//         if(error.name === 'PermissionError'){
//             container.innerHTML = `<a href="/" id="return"> <img src="static/return.svg"></a>
//             <h1 class="text-center"> ${error.message} </h1>
//             `
//             return
//         }
//         if(error.name === 'StatusError'){
//             console.log(error.message)
//             container.insertAdjacentHTML('afterbegin', alertComponent(error.message, 'alert-danger'))
//         }
//         // location.href = '/'
//     }
// }

// window.addEventListener('load', handleLoad);
window.addEventListener('load', initComponent);
