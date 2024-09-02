import { useEffect, useState } from "react";
import LastPredictions from "@/pages/LastPredictions.jsx";
import Prediction from "@/pages/Prediction.jsx";
import AfterPrediction from "@/pages/AfterPrediction.jsx";
import Spinner from "@/components/Spinner";
import { SESSION_CHECK_URL, NO_SESSION_REDIRECT } from "@@/constants";
import { getFromLocalStorage } from "@@/functions";
import { useNavigate } from "react-router-dom";

export default function Index() {
    const [page, setPage] = useState('prediction');
    //El dni que obtengo de verify_session y lo necesito para Experiment.jsx
    const [username, setUsername] = useState(null);
    //Ultimas predicciones (las saco de localStorage)
    const [lastPred, setLastPred] = useState({ posicion: null, velocidad: null, aceleracion: null });
    //Estado para saber si muestro los videos o no en Prediction.jsx
    const [editPredictions, setEditPredictions] = useState(false);
    const navigate = useNavigate();

    // Funcion para verificar si el usuario esta logueado
    const verify_session = async () => {
        try {
            const res = await fetch(SESSION_CHECK_URL, { method: 'POST' });

            if (res.status === 401) return false;

            const data = await res.json();
            return data;
        } catch {
            return false;
        }
    }

    // Funcion para volver a los graficos de predicción cuando ya se guardó
    const editPredictionsHandler = () => {
        setEditPredictions(true);
        setPage('prediction');
    }

    const startPredictionHandler = () => {
        setEditPredictions(true);
        setPage('prediction');
    }

    const finishPredictionHandler = (lastPredictions) => {
        setLastPred(lastPredictions);
        setPage('afterPrediction');
    }

    const startExperimentHandler = () => {
        // Hacer petición para obtener JWT o si ya lo tiene y es válido dejar acceder a experimento
        navigate('/experimento')
    }

    const downloadImages = (imagesArray, type) => {
        if(!imagesArray) return;
        imagesArray.forEach(([magn, img]) => {
            const link = document.createElement('a');
            link.href = img;
            link.download = type + "_" + magn + ".png";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }
    const handleDownload = ([predictions, experimentals]) => {
        if(!predictions && !experimentals) return;
        
        downloadImages(predictions, "Prediccion");
        downloadImages(experimentals, "Experimental");

    }


    // Efecto a ejecutar cuando se renderiza el componente
    useEffect(() => {
        
        verify_session().then(data => {
            
            if (!data) location.href = NO_SESSION_REDIRECT;
            setUsername(data);
        });

        const savedPredictions = getFromLocalStorage("lastPredictions");
        // En caso de que no haya predicciones guardadas
        if (!savedPredictions) {
            setPage('prediction');
            return;
        }

        setLastPred(savedPredictions);
        setPage('lastPrediction');
        
    }, []);

    if (!username) return <Spinner />

    if (page === 'prediction') {
        return <Prediction editPredictions={true} finishPredictionHandler={finishPredictionHandler} />;
    }

    if (page === 'lastPrediction') {
        return <LastPredictions lastPred={Object.entries(lastPred)} handlePredict={startPredictionHandler} handleExperiment={startExperimentHandler} handleDownload={handleDownload}/>;
    }

    if (page === 'afterPrediction') {
        return <AfterPrediction handleEdit={editPredictionsHandler} handleExperiment={startExperimentHandler}handleDownload={handleDownload} lastPredictions={Object.entries(lastPred)} />;
    }

}
