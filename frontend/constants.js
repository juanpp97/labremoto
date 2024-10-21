export const ACCESS_TOKEN = 'access';
export const REFRESH_TOKEN = 'refresh';
export const PRED_POINTS = 'points';
export const LAST_PREDICTIONS = 'lastPredictions';
export const LAST_EXPERIMENT = 'lastExperiment';

/* Produccion */
export const SESSION_CHECK_URL = 'https://labremotos.fica.unsl.edu.ar/session.php'
export const EXPERIMENT_BASE_URL = 'https://labremotos.fica.unsl.edu.ar/raspi'
export const NO_SESSION_REDIRECT = 'https://labremotos.fica.unsl.edu.ar/'
export const GET_TOKEN_URL = EXPERIMENT_BASE_URL
export const CHECK_TOKEN_URL = EXPERIMENT_BASE_URL + 'verificar_token'
export const ANGLE_URL = EXPERIMENT_BASE_URL + 'inclinar'
export const START_EXP_URL = EXPERIMENT_BASE_URL + 'iniciar'
export const RESTART_EXP_URL = EXPERIMENT_BASE_URL + 'reiniciar'
export const POS_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-espacio'
export const VEL_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-velocidad'
export const AC_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-aceleracion'
export const LOGOUT_URL = EXPERIMENT_BASE_URL + 'logout'
export const CAMERA_URL = EXPERIMENT_BASE_URL + 'camera'

/* Development */
// export const SESSION_CHECK_URL = 'http://localhost:8000/session_local.php'
// export const EXPERIMENT_BASE_URL = 'http://localhost:5000/'
// export const GET_TOKEN_URL = EXPERIMENT_BASE_URL
// export const CHECK_TOKEN_URL = EXPERIMENT_BASE_URL + 'verificar_token'
// export const ANGLE_URL = EXPERIMENT_BASE_URL + 'inclinar'
// export const START_EXP_URL = EXPERIMENT_BASE_URL + 'iniciar'
// export const RESTART_EXP_URL = EXPERIMENT_BASE_URL + 'reiniciar'
// export const POS_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-espacio'
// export const VEL_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-velocidad'
// export const AC_GRAPH_URL = EXPERIMENT_BASE_URL + 'resultados/grafica-aceleracion'
// export const LOGOUT_URL = EXPERIMENT_BASE_URL + 'logout'
// export const CAMERA_URL = EXPERIMENT_BASE_URL + 'camera'
// export const NO_SESSION_REDIRECT = '/#/experimento'
