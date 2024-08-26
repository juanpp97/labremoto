export default function Videos() {
    return (
        <>
            <p className="heading">Antes de comenzar el experimento, predice los resultados del mismo a partir de los siguientes videos </p>
            <article className="video">
                <video controls>
                    <source src="src/assets/video_normal.mp4" type="video/mp4" />
                </video>
                <video controls>
                    <source src="src/assets/video_lento.mp4" type="video/mp4" />
                </video>

            </article>
        </>
    )
}