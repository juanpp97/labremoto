import Spinner from "@/components/Spinner";
import Timer from "@/components/Timer";
import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"


export default function Experiment({}){
    const [isLoading, setIsLoading] = useState(true);
    const [isRequestPending, setIsRequestPending] = useState(false)
    //TO DO: useEffect que verifique que efectivamente el usuario pueda estar aca (token en localStorage y válido)

    useEffect(() => {
        console.log("mounted")
        // Verificar si hay token en local storage

        // Verificar si Date.now()/ > jwt.exp*1000 (libreria jwt decode)

        // Si llego hasta aca verificar en el servidor si es el token correcto
        
        //Si se cumplio, verificar cuantos segundos quedan para la expiración del token y modificar el cronometro Math.trunc((jwt.exp * 1000 - Date.now()) / 1000)
        setIsLoading(false);
    }, [])
    return (
        <>
        {
        isLoading ? <Spinner /> :
        <>
        <Timer/>
        <h1> Experimento </h1>
        </>
        }

        </>
    )
}