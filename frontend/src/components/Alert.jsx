
export default function Alert({msg, isError = false}) {
  return (
    <div className="alert ">
        
        <p className="alert__message">{msg}</p>
        
    </div>
  )
}
