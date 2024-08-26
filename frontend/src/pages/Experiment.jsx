import Spinner from "@/components/Spinner";
import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"
export default function Experiment(){
    const [isLoading, setIsLoading] = useState(true);
    //TO DO: useEffect que verifique que efectivamente el usuario pueda estar aca
    useEffect(() => {
        //Verificar que el token sea válido
        setIsLoading(false);
    }, [])
    return (
        <>
        {
        isLoading ? <Spinner /> :
        <>
        <h1> Experimento </h1>
        <NavLink to="/"> Inicio </NavLink>
        </>
        }

        </>
    )
}