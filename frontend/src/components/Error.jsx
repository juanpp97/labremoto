export default function Error({message, isError = false, onClick}){
    return(
        <div className={`alert ${isError ? 'error' : 'success'} animationOpacityIn`}>
            <p className="alert__message">{message}</p>
            <span className="icon" onClick={onClick}>&#x2715;</span>
    
      </div>
    )
}