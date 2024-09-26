import Spinner from "@/components/Spinner";
import { Suspense } from "react";
import Timer from "@/components/Timer";
import CameraFeed from "@/components/CameraFeed";
import { useEffect, useState } from "react";
import { getFromLocalStorage } from "@@/functions";
import { ACCESS_TOKEN, REFRESH_TOKEN, CAMERA_URL } from '@@/constants';
import { useNavigate } from "react-router-dom";
import { jwtDecode } from "jwt-decode";
import { verifyExpired, verifyTokenValidity } from "@@/functions";

export default function Experiment({ }) {
    const [isLoading, setIsLoading] = useState(true);
    const [isRequestPending, setIsRequestPending] = useState(false);
    const [secondsRemaining, setSecondsRemaining] = useState(0);
    const [pitchAngle, setPitchAngle] = useState(0);
    const [lastPitchAngle, setLastPitchAngle] = useState(0);
    const [showCamera, setShowCamera] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        console.log('re-rendered');

    })

    useEffect(() => {
        const auth_verify = async () => {
            console.log("token");
            const token = getFromLocalStorage(ACCESS_TOKEN);

            if (!token) {
                navigate('/');
            }

            try {

                if (verifyExpired(token) || !await verifyTokenValidity(token)) {
                    localStorage.removeItem(ACCESS_TOKEN);
                    localStorage.removeItem(REFRESH_TOKEN);
                    navigate('/');
                }
                const decoded = jwtDecode(token);

                const timeRemaining = Math.trunc((decoded.exp * 1000 - Date.now()) * 0.001);
                setSecondsRemaining(timeRemaining);

            } catch (error) {
                navigate('/');
            } finally {
                setIsLoading(false);
                setShowCamera(true)
            }
        };

        auth_verify();

    }, []);

    const handleAngleChange = (event) => {
        setPitchAngle(event.target.value)
    }
    const increasePitch = () => {
        if(pitchAngle >= 15) return;
        setPitchAngle((prev) => prev + 1)
    }
    const decreasePitch = () => {
        if(pitchAngle <= 0) return;
        setPitchAngle((prev) => prev - 1)
    }
    const validAngle = pitchAngle >= 0 && pitchAngle <= 15; 
    return (
        <>
            {
                isLoading ? <Spinner /> :
                    <>
                        <Timer numSeconds={secondsRemaining} />

                        <section className="experiment">
                            <div className="experiment__feed">
                                <h2 className="feed__heading">Vista en vivo</h2>
                                <p class="pitch"><strong> Angulo de inclinación actual: </strong> {lastPitchAngle}°  </p>
                                {showCamera && <CameraFeed src={CAMERA_URL} />}
                            </div>

                            <div class="experiment_controls">
                                <h2 className="feed__heading">Controles del experimento</h2>
                                <div className="form-group">

                                    <label htmlFor="pitch">Angulo de inclinación</label>
                                    <div className="input-group">
                                        <button type="button" className="icon-button" onClick={decreasePitch}>−</button>
                                        <input type="number" name="pitch" id={`pitch`} className={`pitch_input ${validAngle ? "" : "error-input"}`} onChange={handleAngleChange} min={0} max={15} value={pitchAngle}/>
                                        <button type="button" className="icon-button" onClick={increasePitch}>+</button>
                                    </div>
                                    {!validAngle ?
                                    <p className="error_message"> El angulo debe estar comprendido entre 0° y 15°</p>
                                    : null}
                                </div>
                            </div>
                        </section>
                    </>
            }
        </>
    );
}