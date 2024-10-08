/* eslint-disable react/prop-types */
import Button from "@/components/Button";
import PredictionCanvas from "@/components/PredictionCanvas";
import SaveIcon from "@/components/SaveIcon";
import Videos from "@/components/Videos";
import { getFromLocalStorage } from "@@/functions.js";
import { useEffect, useRef, useState } from "react";

export default function Prediction({ editPredictions, finishPredictionHandler }) {
    const [showCanvas, setShowCanvas] = useState(false);
    const [points, setPoints] = useState({ posicion: [], velocidad: [], aceleracion: [] });
    const lastCanvas = useRef(null);
    const posCanvasRef = useRef(null);
    const velCanvasRef = useRef(null);
    const accCanvasRef = useRef(null);

    const addNewPoint = (point, type) => {
        const newPoints = { ...points };
        newPoints[type].push(point);
        setPoints(newPoints);
    }

    const updateLastCanvas = (canvas) => {
        lastCanvas.current = canvas;
    };

    const handlePointDeletion = (event) => {
    
        if(!lastCanvas.current) return;
        const type = lastCanvas.current.dataset["magnitude"];

        //Deshacer
        if (event.ctrlKey && ['z', 'Z'].includes(event.key)) {
            setPoints(prevPoints => {
                const newPoints = { ...prevPoints };
                if (newPoints[type].length > 0) {
                    newPoints[type].pop();
                }
                return newPoints;
            });
        }
        //Borrar
        if (['b', 'B'].includes(event.key)) {
            setPoints(prevPoints => {
                const newPoints = { ...prevPoints, [type]: [] };
                return newPoints;
            });
        }
    }
    // Cuando se deciden guardar las predicciones
    const handleSave = () => {
        localStorage.setItem('points', JSON.stringify(points));
        // Obtener la codificación base64 de cada canvas
        const canvasList = [posCanvasRef.current, velCanvasRef.current, accCanvasRef.current];
        const lastPred = {posicion: "", velocidad: "", aceleracion: ""};
        canvasList.forEach(canvas => {
            lastPred[canvas.dataset["magnitude"]] = canvas.toDataURL();
        });
        localStorage.setItem('lastPredictions', JSON.stringify(lastPred));
        finishPredictionHandler(lastPred);
    }

    const getCanvasReference = (ref, type) => {
        switch(type){
            case "posicion":
                posCanvasRef.current = ref;
                break;
            case "velocidad":
                velCanvasRef.current = ref;
                break;
            case "aceleracion":
                accCanvasRef.current = ref;
                break;
            
        }

    }

    // Effect a ejecutar al montar el componente
    useEffect(() => {
        document.addEventListener('keydown', handlePointDeletion);
        return () => document.removeEventListener('keydown', handlePointDeletion);
    }, [])


    // Effect para el caso de editar predicciones
    useEffect(() => {
        if (!editPredictions) return;
        const points = getFromLocalStorage("points");
        if (!points) return;
        setPoints(points);
        setShowCanvas(true);
    }, [editPredictions])

    return (
        <section className="prediction">
            {!editPredictions && (
                <>
                    <Videos />

                    {
                        !showCanvas
                        &&
                        <div className="buttons">
                            <Button onClick={() => setShowCanvas(true)}>
                                Estoy listo para predecir!
                            </Button>
                        </div>
                    }
                </>
            )}

            {
                showCanvas && (
                    <>
                    <article className={`prediction__canvas ${showCanvas && "animationIn"}`} >

                        <p><strong>Atajos del teclado: </strong> Presiona <code>B</code> para borrar en la última gráfica utilizada o <code>Ctrl + Z</code> para deshacer el último trazo</p>

                        <div className="canvas" id="prediction_canvas">
                            <PredictionCanvas points={points.posicion} addPoint={addNewPoint} color="red" magnitude="posicion" updateLastCanvas={updateLastCanvas} getRef={getCanvasReference}/>

                            <PredictionCanvas points={points.velocidad} addPoint={addNewPoint} color="green" magnitude="velocidad" updateLastCanvas={updateLastCanvas} getRef={getCanvasReference}/>

                            <PredictionCanvas points={points.aceleracion} addPoint={addNewPoint} color="blue" magnitude="aceleracion" updateLastCanvas={updateLastCanvas} getRef={getCanvasReference}/>
                        </div>

                    </article>
                    <div className="buttons">
                    <button onClick={handleSave}> <SaveIcon width={24} height={24}/> Guardar Predicciones</button>
                    </div>
                    </>
                )
            }

        </section>

    )
}