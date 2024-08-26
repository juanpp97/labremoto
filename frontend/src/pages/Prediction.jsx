/* eslint-disable react/prop-types */
import PredictionCanvas from "@/components/PredictionCanvas";
import Videos from "@/components/Videos";
import {getFromLocalStorage} from "@@/functions.js";
import { useEffect, useState } from "react";

export default function Prediction({editPredictions}) {
    const [showCanvas, setShowCanvas] = useState(false);
    const [points, setPoints] = useState({posicion: [], velocidad: [], aceleracion: []});
    const [lastCanvas, setLastCanvas] = useState(null);

    const addNewPoint = (point, type) => {
        const newPoints = { ...points };
        newPoints[type].push(point);
        setPoints(newPoints);
    }
    // useEffect(() => {
    //     console.log(points);
    // }, [points])
    //Cuando quiero editar la predicción busco los puntos guardados en localStorage y los cargo en el state
    useEffect(() => {
        const points = getFromLocalStorage("points")
        if(!points) return;
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

                    <article className={`prediction__canvas ${showCanvas && "animationIn"}`}>

                        <p><strong>Atajos del teclado: </strong> Presiona <code>B</code> para borrar en la última gráfica utilizada o <code>Ctrl + Z</code> para deshacer el último trazo</p>

                        <div className="canvas">
                           <PredictionCanvas points={points.posicion} addPoint={addNewPoint} color="red" magnitude="posicion" updateLastCanvas={setLastCanvas} />
                           <PredictionCanvas points={points.velocidad} addPoint={addNewPoint} color="green" magnitude="velocidad" updateLastCanvas={setLastCanvas}/>
                           <PredictionCanvas points={points.aceleracion} addPoint={addNewPoint} color="blue" magnitude="aceleracion" updateLastCanvas={setLastCanvas}/>
                        </div>

                    </article>

                )
            }

        </section>

    )
}