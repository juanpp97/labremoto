import DownloadbleImage from "@/components/DownloadbleImage";

export default function lastPredictions({ lastPred, lastExp }) {
    return (
        <>
            <div>
            {lastPred
                ? lastPred.map((img, index) =>
                    <DownloadbleImage key={index} url={img.url} name={img.name} downloadName={img.downloadName} />
                )
                : null
            }
            </div>

            {lastExp
                ? lastExp.map((img, index) =>
                    <DownloadbleImage key={index} url={img.url} name={img.name} downloadName={img.downloadName} />
                )
                : null
            }
        </>
    )

}