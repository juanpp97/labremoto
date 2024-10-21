import Button from "@/components/Button";
import DownloadIcon from "@/components/DownloadIcon";
import DownloadbleImage from "@/components/DownloadbleImage";
import LoginIcon from "@/components/LoginIcon";
import PredictionResults from "@/components/PredictionResults";
import RepeatIcon from "@/components/RepeatIcon";
import Error from "@/components/Error";
import Spinner from "@/components/Spinner";

import { useEffect, useState } from "react";
import ExperimentalResults from "@/components/ExperimentalResults";

export default function lastPredictions({ lastPred, lastExp, handlePredict, handleExperiment, handleDownload, isRequest }) {
    
    return (
        <>
            <PredictionResults predictionEntries={lastPred} text="Tus ultimas predicciones">

                {
                    lastExp
                        ? (
                            <ExperimentalResults text="Tus ultimas gráficas experimentales" lastExp={lastExp}/>
                           
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

                {isRequest ? <Spinner/> : <Button onClick={handleExperiment}> 
                    <LoginIcon width={24} height={24}/> 
                    Iniciar Experimento 
                </Button>}
            </div>
        </>
    )

}