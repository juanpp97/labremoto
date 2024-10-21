import Spinner from "@/components/Spinner";
import Timer from "@/components/Timer";
import CameraFeed from "@/components/CameraFeed";
import Error from "@/components/Error";
import PredictionResults from "@/components/PredictionResults";
import { useEffect, useState } from "react";
import { getFromLocalStorage } from "@@/functions";
import { ACCESS_TOKEN, REFRESH_TOKEN, CAMERA_URL, POS_GRAPH_URL, VEL_GRAPH_URL, AC_GRAPH_URL } from '@@/constants';
import { useNavigate } from "react-router-dom";
import { jwtDecode } from "jwt-decode";
import { verifyExpired, verifyTokenValidity, sendAngle, sendStartExp, getGraphs, sendRestartExp, logout } from "@@/functions";
import ExperimentalResults from "@/components/ExperimentalResults";
import RestartIcon from "@/components/RestartIcon";

export default function Experiment({ }) {
    const [isLoading, setIsLoading] = useState(true);
    const [isRequestPending, setIsRequestPending] = useState(false);
    const [requestType, setRequestType] = useState([0, 0, 0])
    const [secondsRemaining, setSecondsRemaining] = useState(0);
    const [pitchAngle, setPitchAngle] = useState(0);
    const [lastPitchAngle, setLastPitchAngle] = useState(0);
    const [showCamera, setShowCamera] = useState(false);
    const [cameraSrc, setCameraSrc] = useState(CAMERA_URL)
    const [showAlert, setshowAlert] = useState(false);
    const [alertMessage, setAlertMessage] = useState("");
    const [isError, setIsError] = useState(false);
    const [showResults, setShowResults] = useState(false);
    const [lastPred, setLastPred] = useState({ posicion: null, velocidad: null, aceleracion: null });
    const [lastExp, setLastExp] = useState({ posicion: null, velocidad: null, aceleracion: null });

    const navigate = useNavigate();
    const validAngle = pitchAngle >= 0 && pitchAngle <= 15;

    const closeCamera = () => setCameraSrc('');

    useEffect(() => {
        let token;
        const authVerify = async () => {
            try {
                token = getFromLocalStorage(ACCESS_TOKEN);
                if (!token) {
                    navigate('/', {state: {error: true}});
                }               
                if (verifyExpired(token) || !await verifyTokenValidity(token)) {
                    localStorage.removeItem(ACCESS_TOKEN);
                    localStorage.removeItem(REFRESH_TOKEN);
                    navigate('/', {state: {error: true}});
                }
                const decoded = jwtDecode(token);

                const timeRemaining = Math.trunc((decoded.exp * 1000 - Date.now()) * 0.001);
                setSecondsRemaining(timeRemaining);

            } catch (error) {
                localStorage.removeItem(ACCESS_TOKEN);
                localStorage.removeItem(REFRESH_TOKEN);
                navigate('/', {state: {error: true}});
            }finally {
                setIsLoading(false);
                setShowCamera(true)
            }
        }
        const setLastPredictions = () => {
            const savedPredictions = getFromLocalStorage("lastPredictions");
            if(!savedPredictions) return;
            setLastPred(savedPredictions);
            
        }

        authVerify();
        setLastPredictions();

       
    }, []);

    const changeAlertVisibility = (error, message) => {
        setIsError(error);
        setAlertMessage(message);
        setshowAlert(true);
        setTimeout(() => setshowAlert(false), 7000)
    }

    const handleAngleChange = (event) => {
        setPitchAngle(Number(event.target.value))
    }
    const increasePitch = () => {
        if (pitchAngle >= 15) return;
        setPitchAngle((prev) => prev + 1)
    }
    const decreasePitch = () => {
        if (pitchAngle <= 0) return;
        setPitchAngle((prev) => prev - 1)
    }

    const closeAlert = () => setshowAlert(false);

    const sendPitchAngle = async () => {
        if (isRequestPending || !validAngle) return;
        const angle = pitchAngle;
        try {
            setIsRequestPending(true);
            setRequestType([1, 0, 0])
            const token = getFromLocalStorage(ACCESS_TOKEN);
            const res = await sendAngle(token, angle)

            setLastPitchAngle(angle);
            changeAlertVisibility(false, res?.msg || "Rampa inclinada correctamente");
        } catch (error) {
            changeAlertVisibility(true, "Error al enviar el ángulo");
        } finally {
            setRequestType([0, 0, 0])
            setIsRequestPending(false);

        }
    }
    const fetchGraphs = async () => {
        const token = getFromLocalStorage(ACCESS_TOKEN);
        if(!token) navigate('/');
        let acGraph, velGraph, posGraph; 
        try {
            acGraph = await getGraphs(AC_GRAPH_URL, token);
            velGraph = await getGraphs(VEL_GRAPH_URL, token);
            posGraph = await getGraphs(POS_GRAPH_URL, token);
            
        } catch (error) {
            changeAlertVisibility(true, "Error al obtener las gráficas");
            return;
        }finally{
            const expGraphs = {
                posicion: posGraph,
                velocidad: velGraph,
                aceleracion: acGraph
            }
            setLastExp(expGraphs);
            localStorage.setItem('lastExperimentals', JSON.stringify(expGraphs));
            setShowResults(true);
            changeAlertVisibility(false, "Graficas obtenidas correctamente");

        }

    }
    const startExperiment = async () => {
        if (isRequestPending) return;
        let res;
        try {
            setIsRequestPending(true);
            setRequestType([0, 1, 0])
            const token = getFromLocalStorage(ACCESS_TOKEN);
            res = await sendStartExp(token)
        } catch (error) {
            changeAlertVisibility(true, "Error al iniciar el experimento");
            setRequestType([0, 0, 0])
            setIsRequestPending(false);
            return;
        } finally {
            setTimeout(async () => {
                await fetchGraphs();
                setRequestType([0, 0, 0])
                setIsRequestPending(false);
            }, 2000)
            changeAlertVisibility(false, res?.msg || "Experimento realizado con éxito");
            setLastPitchAngle(0);


        }
    }

    const restartExperiment = async () => {
        if (isRequestPending) return;
        let res;
        try {
            setIsRequestPending(true);
            setRequestType([0, 0, 1])
            const token = getFromLocalStorage(ACCESS_TOKEN);
            res = await sendRestartExp(token)
        } catch (error) {
            changeAlertVisibility(true, "Error al reiniciar el experimento");
            setRequestType([0, 0, 0])
            setIsRequestPending(false);
            return;
        }finally{
            changeAlertVisibility(false, res?.msg || "Experimento reiniciado con éxito");
            setLastPitchAngle(0);
            setRequestType([0, 0, 0])
            setIsRequestPending(false);
        }
    }
    const finishExperiment = async () => {
        if (isRequestPending) return;
        let res;
        try {
            setIsRequestPending(true);
            const token = getFromLocalStorage(ACCESS_TOKEN);
            res = await logout(token)
        } catch (error) {
            changeAlertVisibility(true, "Error al reiniciar el experimento");
            setIsRequestPending(false);
            return;
        }finally{
            localStorage.removeItem(ACCESS_TOKEN);
            localStorage.removeItem(REFRESH_TOKEN)
            closeCamera();
            setIsRequestPending(false);
            setTimeout(() => navigate("/"), 100)
        }
    }
    return (
        <>
            {
                isLoading ? <Spinner /> :
                    <>
                        <Timer numSeconds={secondsRemaining} closeCamera={closeCamera} />
                        {showAlert && <Error message={alertMessage} isError={isError} onClick={closeAlert} />}
                        <section className="experiment">
                            <div className="experiment__feed">
                               <h2 className="feed__heading">Vista en vivo</h2> 
                                <p class="pitch"><strong> Angulo de inclinación actual: </strong> {lastPitchAngle}°  </p>
                                {showCamera && <CameraFeed src={cameraSrc} />}
                            </div>

                            <div class="experiment_controls">
                                <h2 className="feed__heading">Controles del experimento</h2>
                                <div className="form-group">

                                    <label htmlFor="pitch">Angulo de inclinación</label>
                                    <div className="input-group">

                                        <button type="button" className="icon-button" onClick={decreasePitch}>−</button>

                                        <input type="number" name="pitch" id={`pitch`} className={`pitch_input ${validAngle ? "" : "error-input"}`} onChange={handleAngleChange} min={0} max={15} value={pitchAngle} />

                                        <button type="button" className="icon-button" onClick={increasePitch}>+</button>
                                    </div>
                                    {!validAngle ?
                                        <p className="error_message"> El angulo debe estar comprendido entre 0° y 15°</p>
                                        : null}


                                </div>
                                <div className="control__buttons">
                                    {requestType[0] ? <Spinner /> : <button type="button" className="icon-button" onClick={sendPitchAngle}>Enviar ángulo</button>}
                                    {requestType[1] ? <Spinner /> : <button type="button" className="icon-button" onClick={startExperiment}>Iniciar experimento</button>}
                                    {requestType[2] ? <Spinner /> : <button type="button" className="icon-button" onClick={restartExperiment}>Reiniciar experimento</button>}
                                     <button type="button" className="icon-button" onClick={finishExperiment}>Finalizar experimento</button>

                                </div>
                            </div>
                        </section>
                        
                        {
                            showResults && <section className="results">
                            <PredictionResults predictionEntries={Object.entries(lastPred)} text="Predicciones">
                                {lastExp["posicion"] && lastExp["velocidad"] && lastExp["aceleracion"] 
                                ?  
                                (
                                <ExperimentalResults text="Experimentales" lastExp={Object.entries(lastExp)}/>                               
                                )
                                : null
                                }
        
                            </PredictionResults>


                        </section>
                        }
    

                    </>
            }
        </>
    );
}