import { useEffect } from "react"

export default function Timer({}){
    useEffect(() => {
        console.log("Timer mounted")
    }, [])
    return(
        <h1> Timer </h1>
    )
}