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

export default function Experiment({}) {
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

    return (
        <>
            {
                isLoading ? <Spinner /> :
                    <>
                     <Timer numSeconds = {secondsRemaining}/>

                        <section className="experiment">
                            <div className="experiment__feed">
                                <h2 className="feed__heading">Vista en vivo</h2>
                                <p class="pitch"><strong> Angulo de inclinación actual: </strong> {lastPitchAngle}°  </p>
                                { showCamera &&  <CameraFeed src={CAMERA_URL} />}
                            </div>

                            <div class="experiment_controls">
                                <h2 className="feed__heading">Controles del experimento</h2>
                                <label htmlFor="pitch">Angulo de inclinación</label>
                                <input type="number" name="pitch" id="pitch" className="pitch_input" onChange={handleAngleChange}/>
                                <p>{pitchAngle}</p>
                            </div>
                        </section>
                    </>
            }
        </>
    );
}