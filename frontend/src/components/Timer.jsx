import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom";
import { ACCESS_TOKEN, REFRESH_TOKEN } from '@@/constants';


export default function Timer({numSeconds, closeCamera}){
    const [secondsRemaining, setSecondsRemaining] = useState(numSeconds)
    const navigate = useNavigate();
    const minutes = Math.trunc(secondsRemaining / 60);;
    const seconds = secondsRemaining % 60;

    useEffect(() => {
        const timer = setInterval(() => {
            setSecondsRemaining(prev => {
                if (prev <= 1) {
                    closeCamera();
                    setTimeout(() => {
                        clearInterval(timer);
                        localStorage.removeItem(ACCESS_TOKEN);
                        localStorage.removeItem(REFRESH_TOKEN);
                        navigate("/");
                    }, 100)
                }
                return prev - 1;
            });
        }, 1000);
        return () => clearInterval(timer)
    }, [])
    return(
        <div className="timer">
            <p> <strong>Tiempo restante:</strong> {minutes} : {seconds >= 10 ? seconds : `0${seconds}`} </p>
        </div>
    )
}