import { Routes, Route, HashRouter, Navigate} from "react-router-dom"
import Index from '@/pages/Index.jsx'
import Experiment from '@/pages/Experiment.jsx'
function App() {

  return (
    <>
      <HashRouter>
        <Routes>
          <Route exact path = "/" element = {<Index />}/>
          <Route path = "/experimento" element = {<Experiment />}/>
          <Route path = "*" element = {<Navigate to="/" />}/>
        </Routes>
      </HashRouter>
    </>
  )
}

export default App
