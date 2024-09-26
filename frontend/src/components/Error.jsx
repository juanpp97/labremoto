export default function Error({message, onClick}){
    return(
        <div className="alert animationOpacityIn">
            {message}
            <span className="icon" onClick={onClick}>&#x2715;</span>
    
      </div>
    )
}