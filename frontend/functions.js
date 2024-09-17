import { CHECK_TOKEN_URL } from '@@/constants'
import { jwtDecode } from "jwt-decode";


const getFromLocalStorage = (key) => {

    if (typeof localStorage === "undefined" || !localStorage.getItem(key)) {
        return null
    }
    return JSON.parse(localStorage.getItem(key));
}

const getTokenFromServer = () => {
    //Peticion hacia el servidor para obtener el token
}

const verifyTokenValidity = async (token) => {
    try {
        
        const res = await fetch(CHECK_TOKEN_URL, {
            method: "GET",
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });
        if (!res.ok) return false;
        return res.status === 200;
    } catch (error) {
        console.error('Error verifying token:', error);
        return false;
    }
};

const verifyExpired = (token) =>{
    const decoded = jwtDecode(token);

    return Date.now() > decoded.exp * 1000
}
export { getFromLocalStorage, getTokenFromServer, verifyTokenValidity, verifyExpired };