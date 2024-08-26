/* eslint-disable react/prop-types */
export default function DownloadbleImage({ url, name, downloadName }) {
    return (
        <a download={downloadName} href={url} title={name}>
            <img alt={name} src={url}/>
        </a>
    )
}