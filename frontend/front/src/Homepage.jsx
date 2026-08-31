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
            NEPSEIntel turns raw NEPSE end-of-day data into strategies you can
            actually check. Eight strategies, one shared execution model with
            costs charged on both sides of every trade, and regime detection that
            only ever reads bars it would have had at the time.
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
            <h3>Event-Driven Backtesting</h3>
            <p>Eight strategies over a single execution model. Entries fill at the next bar's open, and fee plus slippage is charged on entry and again on exit.</p>
          </div>
          <div className="spec-item">
            <span className="spec-label">02 / ROBUSTNESS</span>
            <h3>Out-Of-Sample Selection</h3>
            <p>Auto Strategy picks on an earlier slice of history and reports results on the later slice it never saw, so the choice is not scored on the data that made it.</p>
          </div>
          <div className="spec-item">
            <span className="spec-label">03 / REGIME</span>
            <h3>Filtered HMM Detection</h3>
            <p>Hidden-state regimes with the state count chosen by BIC, decoded forward-only. Each label uses that bar and earlier ones, never later ones.</p>
          </div>
        </div>

        <p className="data-caveat">
          <strong>Known data limitation:</strong> NEPSE prices here are not adjusted
          for bonus issues, splits or rights. A return measured across a corporate
          action will be wrong, and the artificial gap can read as a volatility
          regime change that never happened. Check the symbol's corporate action
          history before trusting a long window.
        </p>
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
