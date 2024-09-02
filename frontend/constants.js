export const ACCESS_TOKEN = 'access';
export const REFRESH_TOKEN = 'refresh';
export const PRED_POINTS = 'points';
export const LAST_PREDICTIONS = 'lastPredictions';
export const LAST_EXPERIMENT = 'lastExperiment';

/* Produccion */
// export const SESSION_CHECK_URL = 'https://labremotos.fica.unsl.edu.ar/verificar_sesion.php'
//export const EXPERIMENT_URL = 'https://labremotos.fica.unsl.edu.ar/raspi'
//export const NO_SESSION_REDIRECT = ''

/* Development */
export const SESSION_CHECK_URL = 'http://localhost:8000/session_local.php'
export const EXPERIMENT_BASE_URL = 'http://localhost:5000/'
export const NO_SESSION_REDIRECT = '/#/experimento'
