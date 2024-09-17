import Spinner from "@/components/Spinner";
import Timer from "@/components/Timer";
import { useEffect, useState } from "react";
import { getFromLocalStorage } from "@@/functions";
import { ACCESS_TOKEN, REFRESH_TOKEN } from '@@/constants';
import { useNavigate } from "react-router-dom";
import { jwtDecode } from "jwt-decode";
import { verifyExpired, verifyTokenValidity } from "../../functions";

export default function Experiment({}) {
    const [isLoading, setIsLoading] = useState(true);
    const [isRequestPending, setIsRequestPending] = useState(false);
    const [secondsRemaining, setSecondsRemaining] = useState(0);
    const [pitchAngle, setPitchAngle] = useState(0);

    const navigate = useNavigate();
    const minutes = Math.trunc(secondsRemaining / 60);
    const seconds = Math.trunc(secondsRemaining % 60);

    useEffect(() => {
        const auth_verify = async () => {
            const token = getFromLocalStorage(ACCESS_TOKEN);

            if (!token) {
                navigate('/');
                return;
            }

            try {
                const decoded = jwtDecode(token);

                if (verifyExpired(token) || !await verifyTokenValidity(token)) {

                    navigate('/');
                    return;
                }

                const timeRemaining = Math.trunc((decoded.exp * 1000 - Date.now()) * 0.001);
                setSecondsRemaining(timeRemaining);
                
                const timer = setInterval(() => {
                    setSecondsRemaining(prev => {
                        if (prev <= 1) {
                            navigate("/");
                            clearInterval(timer);
                        }
                        return prev - 1;
                    });
                }, 1000);

                return () => clearInterval(timer);
                
            } catch (error) {
                navigate('/');
            } finally {
                setIsLoading(false);
            }
        };

        auth_verify();
    }, []);

    return (
        <>
            {
                isLoading ? <Spinner /> :
                    <>
                        <p>{minutes} : {seconds >= 10 ? seconds : `0${seconds}`}</p>
                        <Timer />
                        <h1> Experimento </h1>
                    </>
            }
        </>
    );
}