/* eslint-disable react/prop-types */
import PredictionCanvas from "@/components/PredictionCanvas";
import Videos from "@/components/Videos";
import { getFromLocalStorage } from "@@/functions.js";
import { useEffect, useRef, useState } from "react";

export default function Prediction({ editPredictions, finishPredictionHandler }) {
    const [showCanvas, setShowCanvas] = useState(false);
    const [points, setPoints] = useState({ posicion: [], velocidad: [], aceleracion: [] });
    const lastCanvas = useRef(null);


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

    const handleSave = () => {
        localStorage.setItem('points', JSON.stringify(points));
        finishPredictionHandler();
    }

    useEffect(() => {
        document.addEventListener('keydown', handlePointDeletion);
        return () => document.removeEventListener('keydown', handlePointDeletion);
    }, [])



    useEffect(() => {
        if (!editPredictions) return;
        const points = getFromLocalStorage("points")
        if (!points) return;
        setPoints(points)

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
                            <button onClick={() => setShowCanvas(true)}>Estoy listo para predecir!</button>
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
                            <PredictionCanvas points={points.posicion} addPoint={addNewPoint} color="red" magnitude="posicion" updateLastCanvas={updateLastCanvas} />
                            <PredictionCanvas points={points.velocidad} addPoint={addNewPoint} color="green" magnitude="velocidad" updateLastCanvas={updateLastCanvas} />
                            <PredictionCanvas points={points.aceleracion} addPoint={addNewPoint} color="blue" magnitude="aceleracion" updateLastCanvas={updateLastCanvas} />
                        </div>

                    </article>
                    <div className="buttons">
                    <button onClick={handleSave}>Guardar Predicciones</button>
                    </div>
                    </>
                )
            }

        </section>

    )
}