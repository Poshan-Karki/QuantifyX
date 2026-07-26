import React from 'react';
import { useNavigate } from 'react-router-dom';
import './Homepage.css';

const Homepage = () => {
  const navigate = useNavigate();

  return (
    <div className="quantifyx-firm">
      {/* Hero Section */}
      <main className="firm-hero">
        <div className="hero-content">
          <p className="sub-title">QUANTITATIVE RESEARCH & STRATEGY VALIDATION</p>
          <h1>Institutional-grade backtesting for the next generation of alpha.</h1>
          <p className="hero-description">
            NEPSEIntel provides the high-performance infrastructure required to transform 
            raw market data into validated, executable strategies. No bias. No latency. 
            Pure mathematical rigor.
          </p>
          <div className="action-area">
            <button className="btn-firm" onClick={() => navigate('/Backtest')}>
              ENTER INFRASTRUCTURE
            </button>
            <span className="access-text">SECURE_CHANNEL_v1.04</span>
          </div>
        </div>
      </main>

      {/* Technical Specifications Grid */}
      <section className="technical-specs">
        <div className="spec-row">
          <div className="spec-item">
            <span className="spec-label">01 / ENGINE</span>
            <h3>Dual-Core Backtesting</h3>
            <p>Seamlessly toggle between vectorized hypothesis testing and event-driven trade execution engines.</p>
          </div>
          <div className="spec-item">
            <span className="spec-label">02 / ROBUSTNESS</span>
            <h3>Statistical Validation</h3>
            <p>Monte Carlo simulations and walk-forward analysis integrated into every research workflow.</p>
          </div>
          <div className="spec-item">
            <span className="spec-label">03 / DATA</span>
            <h3>Timescale Architecture</h3>
            <p>Low-latency access to split-adjusted OHLCV data via institutional-grade pipelines.</p>
          </div>
        </div>
      </section>

      {/* Footer Area */}
      <footer className="firm-footer">
        <div className="footer-line"></div>
        <div className="footer-content">
          <div className="footer-left">
            <span>STRICTLY FOR QUANTITATIVE RESEARCH PURPOSES</span>
          </div>
          <div className="footer-right">
            <span>EST. 2024</span>
            <span className="version">V1.0.4-STABLE</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Homepage;
