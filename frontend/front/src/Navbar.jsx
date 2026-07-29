// Navbar.jsx
import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "./api";
import './Navbar.css';

function Navbar() {
  const [dataStatus, setDataStatus] = useState(null);

  useEffect(() => {
    fetch(apiUrl("/data-status"))
      .then((res) => res.json())
      .then((data) => {
        if (data && data.latest_date) setDataStatus(data);
      })
      .catch(() => {});
  }, []);

  return (
    <nav className="firm-nav">
      <div className="nav-left">
        <Link to="/" className="firm-logo">NEPSEIntel<span>.</span></Link>
        <div className="status-indicator" title="QuantifyX runs on historical end-of-day data, not a live market feed">
          <span className="dot"></span>
          {dataStatus ? `DATA AS OF ${dataStatus.latest_date}` : "HISTORICAL DATA"}
        </div>
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
