const getFromLocalStorage = (key) => {
    if (typeof localStorage === "undefined" || !localStorage.getItem(key)) {
        return null
    }
    return JSON.parse(localStorage.getItem(key))
}

const getTokenFromServer = () => {
    //Peticion hacia el servidor para obtener el token
}

const verifyTokenValidity = () => {
    //Peticion hacia el servidor para verificar si el token de localStorage

}

export { getFromLocalStorage, getTokenFromServer, verifyTokenValidity };