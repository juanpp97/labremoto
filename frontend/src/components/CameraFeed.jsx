import React from 'react'

const CameraFeed = React.memo(({ src }) => {
    return <img src={src} alt="Vista en vivo" className="feed__camera"/>;
  });

export default CameraFeed;