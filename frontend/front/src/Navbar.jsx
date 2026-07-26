// Navbar.jsx
import React from "react";
import { Link } from "react-router-dom";
import './Navbar.css';

function Navbar() {
  return (
    <nav className="firm-nav">
      <div className="nav-left">
        <Link to="/" className="firm-logo">NEPSEIntel<span>.</span></Link>
        <div className="status-indicator"><span className="dot"></span> LIVE_FEED</div>
      </div>
      <ul className="nav-links">
        <li><Link to="/">Home</Link></li>
        <li><Link to="/Backtest">Backtest</Link></li>
        <li><Link to="/Ai">AI Hypothesis</Link></li>
      </ul>
    </nav>
  );
}
export default Navbar;
