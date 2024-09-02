import Button from "@/components/Button";
import DownloadIcon from "@/components/DownloadIcon";
import DownloadbleImage from "@/components/DownloadbleImage";
import LoginIcon from "@/components/LoginIcon";
import PredictionResults from "@/components/PredictionResults";
import RepeatIcon from "@/components/RepeatIcon";
import { useEffect, useState } from "react";

export default function lastPredictions({ lastPred, lastExp, handlePredict, handleExperiment, handleDownload }) {
    const [entries, setEntries] = useState([]);

    useEffect(() => {
        setEntries([lastPred, lastExp]);
    }, [lastPred, lastExp]);


    return (
        <>
            <PredictionResults predictionEntries={lastPred}>

                {
                    lastExp
                        ? (
                            <>
                                <h2>Tus ultimas gráficas experimentales</h2>
                                <div className="images">
                                    {lastExp
                                        ? lastExp.map(([type, img], index) =>
                                            <DownloadbleImage key={index} url={img} name={type} downloadName={"Prediccion_" + type + ".png"} />
                                        )
                                        : null
                                    }
                                </div>
                            </>
                        )
                        : null
                }
            </PredictionResults>
            <div className="buttons">

                <Button onClick={handlePredict}>
                     <RepeatIcon width={24} height={24}/>
                     Repetir predicciones 
                </Button>

                <Button onClick={() => handleDownload(entries)}> 
                    <DownloadIcon width={24} height={24}/> 
                    Descargar gráficos 
                </Button>

                <Button onClick={handleExperiment}> 
                    <LoginIcon width={24} height={24}/> 
                    Iniciar Experimento 
                </Button>
            </div>
        </>
    )

}