
import DownloadbleImage from "@/components/DownloadbleImage";

export default function ExperimentalResults({lastExp, text}) {
    return (
        <>
            <h2>{text}</h2>
            <div className="images">
                {lastExp.map(([type, img], index) =>
                    <DownloadbleImage key={index} url={img} name={type} downloadName={"Experimento_" + type + ".png"} />
                )
                }
            </div>
        </>
    )
}
