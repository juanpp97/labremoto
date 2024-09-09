import videoNormal from '@/assets/video_normal.mp4';
import videoLento from '@/assets/video_lento.mp4';
export default function Videos() {
    return (
        <>
            <p className="heading">Antes de comenzar el experimento, predice los resultados del mismo a partir de los siguientes videos </p>
            <article className="video">
                <video controls>
                    <source src={videoNormal} type="video/mp4" />
                </video>
                <video controls>
                    <source src={videoLento} type="video/mp4" />
                </video>

            </article>
        </>
    )
}