import './App.css'
import Navbar from './Navbar'
import {Routes,Route} from 'react-router-dom'
import Ai from "./Ai"
import Homepage from './Homepage'
import Backtest from './Backtest'

function App() {
  return (
    
    <>
    <Navbar/>
  
    <Routes>
      <Route path='/' element={<Homepage/>}/>
      <Route path="/Ai" element={<Ai/>}/>
      <Route path="/Backtest" element={<Backtest/>}/>
    </Routes>

    
  
      
    </>
  )
}

export default App
