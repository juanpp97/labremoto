/* eslint-disable react/prop-types */
import { useEffect, useRef, useState } from "react"

export default function PredictionCanvas({points, addPoint, color, magnitude, updateLastCanvas, getRef}) {
    const ref = useRef(null);
    const [ctx, setCtx] = useState(null);

    const marginWidth = 20;
    let name = "";
    switch(magnitude){
        case "posicion":
            name = "Posición";
            break;
        case "velocidad":
            name = "Velocidad";
            break;
        case "aceleracion":
            name = "Aceleración";
            break;
        default:
            break;
    }

    
    useEffect(() => {
        const canvas = ref.current;
        getRef(ref.current, magnitude)
        const ctx = canvas.getContext("2d");
        setCtx(ctx);
    }, [])

    useEffect(() => {
        if (!ctx) return;
        const width = ref.current.width;
        const height = ref.current.height;
        drawAxis(ctx, width, height);
        if(!points) return;
        drawPreviousPoints(ctx);
        
    }, [ctx, points, points.length]);



    const getCoordinates = (event) => {
        if (!ctx) return;
        updateLastCanvas(ref.current);
        const width = ref.current.width;
        const height = ref.current.height;
        const gridWidth = (width - marginWidth)/6;
        const gridHeight = height/7;

        //Determinar coordenadas del elemento canvas
        const rect = ref.current.getBoundingClientRect();
        //Determinar posición relativa del mouse
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;

        //Que no se pueda dibujar en la zona de los ejes
        if (x < gridWidth || y > height - gridHeight || y < gridHeight || x > width - marginWidth) return;

        const lastPoint = points.at(-1);
        draw(ctx, x, y, lastPoint);
        addPoint({x: x, y: y}, magnitude);
    }
    const draw = (ctx, x, y, lastPoint) => {
        //Dibujo el punto en donde se hizo click
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();

        if (!points.length || !lastPoint) {
            ctx.moveTo(x, y);
            return;
        }

        /* Dibujo la linea entre los ultimos puntos */
        ctx.beginPath();
        ctx.lineWidth = 2;
        ctx.moveTo(lastPoint.x, lastPoint.y);
        ctx.lineTo(x, y);
        ctx.stroke();
    }

    const drawPreviousPoints = (ctx) => {

        if (points.length > 0) {
            points.forEach((point, index) => {
                const lastPoint = index == 0 ? undefined : points[index - 1];
                draw(ctx, point.x, point.y, lastPoint);
            });
        }
    }
    const drawNumber = (ctx, num, posX, posY) => {
        ctx.font = "13px sans-serif";
        ctx.fillStyle = "black";
        const text = num == 1
                    ? num.toFixed(0).toString()
                    : num.toFixed(1).toString();
        ctx.textAlign = 'left';
        ctx.fillText(text, posX, posY);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    const setLabels = (ctx, width, height, gridWidth, gridHeight) => {
        
        // Eje horizontal
        ctx.font = "bold 15px sans-serif";
        ctx.fillText("Tiempo", (width - marginWidth) / 2, height - 5);
        
        //Eje vertical
        ctx.font = "bold 17px sans-serif";
        ctx.textAlign = 'center';
        ctx.translate(20, height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(name, 0, 0);
        ctx.setTransform(1, 0, 0, 1, 0, 0);

        // Titulo
        ctx.font = "bold 20px sans-serif";
        ctx.textAlign = 'center';
        let title = "Predicción: " + name;

        ctx.translate((width - marginWidth + gridWidth) / 2, gridHeight / 2);
        ctx.fillText(title, 0, 0);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
    const drawAxis = (ctx, width, height) => {
        const gridWidth = (width - marginWidth)/6;
        const gridHeight = height/7;
        
        // Inicializo el canvas en blanco
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, width, height);

        //Determino el estilo de linea de la grilla
        ctx.strokeStyle = '#eee';
        ctx.lineWidth = 1.5;
        ctx.beginPath();

        //Eje horizontal (incluido el 0)
        let axis = 0;
        for (let x = gridWidth; x <= width - marginWidth; x += gridWidth) {
            ctx.moveTo(x, gridHeight);
            ctx.lineTo(x, height - gridHeight);
            if (axis == 0) {
                drawNumber(ctx, axis, gridWidth - 25, height - 30);
            } else {
                drawNumber(ctx, axis, x - 8, height - 25);
            }
            axis += 0.2;
        }

        // Eje vertical
        axis = 0;
        for (let y = height - gridHeight; y >= gridHeight; y -= gridHeight) {
            ctx.moveTo(gridWidth, y);
            ctx.lineTo(width - marginWidth, y);
            if (axis != 0) {
                if (axis == 1) {
                    drawNumber(ctx, axis, gridWidth - 15, y + 5);
                } else {
                    drawNumber(ctx, axis, gridWidth - 25, y + 5);
                }
            }
            axis += 0.2;
        }
        ctx.stroke();
        setLabels(ctx, width, height, gridWidth, gridHeight);

    }
    
    return (
        <>
        <canvas className={"prediccion_" + magnitude} height="300" width="370" ref={ref} onClick={getCoordinates} data-magnitude={magnitude}></canvas>
        </>
    )
}