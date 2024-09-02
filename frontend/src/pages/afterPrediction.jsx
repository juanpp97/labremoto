import PredictionResults from "@/components/PredictionResults";
import Button from "@/components/Button";
import EditIcon from "@/components/EditIcon";
import DownloadIcon from "@/components/DownloadIcon";
import LoginIcon from "@/components/LoginIcon";
export default function afterPrediction({lastPredictions, handleDownload, handleEdit, handleExperiment}){
    return (
        <div className="images_container">

        <PredictionResults predictionEntries={lastPredictions} />
        <div className="buttons">
        <Button onClick={handleEdit}> 
            <EditIcon width={24} height={24}/> 
            Editar predicciones 
        </Button>

        <Button onClick={() => handleDownload([lastPredictions])}> 
            <DownloadIcon width={24} height={24}/> 
            Descargar gráficos 
        </Button>

        <Button onClick={handleExperiment}> 
            <LoginIcon width={24} height={24}/> 
            Iniciar Experimento 
        </Button>

        </div>
        </div>
    )
}