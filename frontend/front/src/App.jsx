import './App.css'
import { Routes, Route } from 'react-router-dom'
import Navbar from './Navbar'
import ErrorBoundary from './ErrorBoundary'
import Ai from './Ai'
import Homepage from './Homepage'
import Backtest from './Backtest'

function App() {
  return (
    <>
      <Navbar />
      <ErrorBoundary>
        <Routes>
          <Route path='/' element={<Homepage />} />
          <Route path='/Ai' element={<Ai />} />
          <Route path='/Backtest' element={<Backtest />} />
        </Routes>
      </ErrorBoundary>
    </>
  )
}

export default App
