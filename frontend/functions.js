import { CHECK_TOKEN_URL, GET_TOKEN_URL, ANGLE_URL, START_EXP_URL, RESTART_EXP_URL, LOGOUT_URL } from '@@/constants'
import { jwtDecode } from "jwt-decode";


const getFromLocalStorage = (key) => {

    if (typeof localStorage === "undefined" || !localStorage.getItem(key)) {
        return null
    }
    return JSON.parse(localStorage.getItem(key));
}

const getTokenFromServer = async (username) => {
    //Peticion hacia el servidor para obtener el token
    try {
        
        const res = await fetch(GET_TOKEN_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
              },
            body: JSON.stringify({ username: "12345678" }),
        });
        const data = await res.json();
        
        return {
            data: data,
            error: res.status !== 200
        };
    } catch (error) {
        console.error('Error authenticating');
        return false;
    }
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

const sendAngle = async (token, angle) => {
    let formData = new FormData();
    formData.append("angulo", angle);
    
    
    const res = await fetch(ANGLE_URL, {
        method: 'POST',
        headers: {
            'Authorization': 'Bearer ' + token
        },
        body: formData
    })
    const data = await res.json();
    if(!res.ok) throw new Error(data?.msg || "Ha ocurrido un error")
    return data
}

const sendStartExp = async(token) => {
    const res = await fetch(START_EXP_URL, {
        method: 'GET',
        headers: {
            'Authorization': 'Bearer ' + token
        }
    })
    const data = await res.json();
    if(!res.ok) throw new Error(data?.msg || "Ha ocurrido un error")
    return data
}

const getGraphs = async (url, token) => {
        const res = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer ' + token
            }
        })
        const blob = await res.blob();
        if(!res.ok) throw new Error("Error al obtener la gráfica")
        return new Promise((resolve, _) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
}

const sendRestartExp = async (token) => {
    const res = await fetch(RESTART_EXP_URL, {
        method: 'GET',
        headers: {
            'Authorization': 'Bearer ' + token
        }
    })
    const data = await res.json();
    if(!res.ok) throw new Error(data?.msg || "Ha ocurrido un error")
    return data
}

const logout = async (token) => {
    const res = await fetch(LOGOUT_URL, {
        method: 'DELETE',
        headers: {
            'Authorization': 'Bearer ' + token
        }
    })
    const data = await res.json();
    if(!res.ok) throw new Error(data?.msg || "Ha ocurrido un error")
    return data
}
export { getFromLocalStorage, getTokenFromServer, verifyTokenValidity, verifyExpired, sendAngle, sendStartExp, getGraphs, sendRestartExp, logout };