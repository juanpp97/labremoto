import DownloadbleImage from "@/components/DownloadbleImage";

export default function PredictionResults({predictionEntries, children}){
    return (
        <div className="images_container animationOpacityIn">

            <h2>Tus ultimas predicciones</h2>
            <div className="images">
            {predictionEntries
                ? predictionEntries.map(([type, img], index) =>
                    <DownloadbleImage key={index} url={img} name={type} downloadName={"Prediccion_" + type + ".png"} />
                )
                : null
            }
            </div>

            {
            children 
                    ? children
                    : null
            }

            
        </div>
    )
}