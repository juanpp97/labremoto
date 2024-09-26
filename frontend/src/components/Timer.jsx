import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom";


export default function Timer({numSeconds}){
    const [secondsRemaining, setSecondsRemaining] = useState(numSeconds)
    const navigate = useNavigate();
    const minutes = Math.trunc(secondsRemaining / 60);;
    const seconds = secondsRemaining % 60;

    useEffect(() => {
        const timer = setInterval(() => {
            setSecondsRemaining(prev => {
                if (prev <= 1) {
                    navigate("/");
                    clearInterval(timer);
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