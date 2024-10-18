import { useEffect, useState } from "react";
import LastPredictions from "@/pages/LastPredictions.jsx";
import Prediction from "@/pages/Prediction.jsx";
import AfterPrediction from "@/pages/AfterPrediction.jsx";
import Spinner from "@/components/Spinner";
import Error from "@/components/Error";
import { SESSION_CHECK_URL, NO_SESSION_REDIRECT, ACCESS_TOKEN, REFRESH_TOKEN } from "@@/constants";
import { getFromLocalStorage, getTokenFromServer } from "@@/functions";
import { useNavigate } from "react-router-dom";
import { verifyExpired } from "../../functions";

export default function Index() {
    const [page, setPage] = useState('prediction');
    //El dni que obtengo de verify_session y lo necesito para Experiment.jsx
    const [username, setUsername] = useState(null);
    //Ultimas predicciones (las saco de localStorage)
    const [lastPred, setLastPred] = useState({ posicion: null, velocidad: null, aceleracion: null });
    const [lastExp, setlastExp] = useState({ posicion: null, velocidad: null, aceleracion: null });
    //Estado para saber si muestro los videos o no en Prediction.jsx
    const [editPredictions, setEditPredictions] = useState(false);
    const [isError, setIsError] = useState(false)
    const [isErrorVisible, setIsErrorVisible] = useState(false);

    const [errorMessage, setErrorMessage] = useState("")
    const [isRequestPending, setIsRequestPending] = useState(false);

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

    // Función para predecir los resultados o repetir predicciones
    const startPredictionHandler = () => {
        setEditPredictions(false);
        setPage('prediction');
    }
    // Cuando el usuario terminó las predicciones
    const finishPredictionHandler = (lastPredictions) => {
        setLastPred(lastPredictions);
        setPage('afterPrediction');
    }
    // Para iniciar el experimento
    const startExperimentHandler = async () => {
        if(isError || isRequestPending) return;
        setIsRequestPending(true);
        const access = getFromLocalStorage(ACCESS_TOKEN);
                
        if(access){
            if(!verifyExpired(access)){
                navigate("/experimento");
                return;
            }
            localStorage.removeItem(ACCESS_TOKEN);
            localStorage.removeItem(REFRESH_TOKEN);
        }
        const data = await getTokenFromServer(username);
        
        if(data.error){
            setErrorMessage(data.data?.msg ?? "Error");
            setIsError(true);
            setIsErrorVisible(true);
            setIsRequestPending(false);
            setTimeout(() => {setIsError(false)}, 60000)
            return;
        }
        const token = data.data;
        localStorage.setItem(ACCESS_TOKEN, JSON.stringify(token?.access))
        localStorage.setItem(REFRESH_TOKEN, JSON.stringify(token?.refresh ?? ""))
        setIsRequestPending(false);

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
        const savedExperimental = getFromLocalStorage("lastExperimentals");
        
        // En caso de que no haya predicciones guardadas
        if (!savedPredictions) {
            setPage('prediction');
            return;
        }

        setLastPred(savedPredictions);
        setlastExp(savedExperimental);
        setPage('lastPrediction');
        
    }, []);

    if (!username) return <Spinner />
    if (page === 'prediction') {
        return <Prediction editPredictions={editPredictions} finishPredictionHandler={finishPredictionHandler} />;
    }

    if (page === 'lastPrediction') {
        return (
        <>
        {isErrorVisible && <Error isError={true} message={errorMessage} onClick = {() => setIsErrorVisible(false)}/>}
        <LastPredictions lastPred={Object.entries(lastPred)} lastExp={lastExp ? Object.entries(lastExp) : null} handlePredict={startPredictionHandler} handleExperiment={startExperimentHandler} handleDownload={handleDownload} />
        
        </>
        )
    }

    if (page === 'afterPrediction') {
        return <AfterPrediction handleEdit={editPredictionsHandler} handleExperiment={startExperimentHandler} handleDownload={handleDownload} lastPredictions={Object.entries(lastPred)} />;
    }

}
