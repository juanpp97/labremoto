// /* eslint-disable react/prop-types */
import { useEffect, useRef, useState } from "react"

export default function PredictionCanvas({points, addPoint, color, magnitude}) {
    const ref = useRef(null);
    const [ctx, setCtx] = useState(null);

    const marginWidth = 20;
    
    useEffect(() => {

        const canvas = ref.current;
        const ctx = canvas.getContext("2d");
        setCtx(ctx);
    }, [])


    useEffect(() => {
        if (!ctx) return;
        const width = ref.current.width;
        const height = ref.current.height;

        drawAxis(ctx, width, height);
        
    }, [ctx]);

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

    const setLabels = (ctx, width, height) => {
        // Eje horizontal
        ctx.font = "bold 15px sans-serif";
        ctx.fillText("Tiempo", (width - marginWidth) / 2, height - 5);
      
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
        setLabels(ctx. width, height);
    }
    
    return (
        <>
        <canvas height="300" width="370" ref={ref}></canvas>
        </>
    )
}