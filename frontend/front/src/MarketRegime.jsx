
import React, { useState, useEffect } from "react";

const REGIME_COLORS = {
  "Trending Up":      { bg: "rgba(34,197,94,0.15)", border: "#22c55e", text: "#86efac" },
  "Trending Down":    { bg: "rgba(239,68,68,0.15)",  border: "#ef4444", text: "#fca5a5" },
  "High Volatility":  { bg: "rgba(234,179,8,0.15)",  border: "#eab308", text: "#fde047" },
  "Low Volatility":   { bg: "rgba(99,102,241,0.15)", border: "#6366f1", text: "#a5b4fc" },
  "Ranging/Sideways": { bg: "rgba(148,163,184,0.15)",border: "#94a3b8", text: "#cbd5e1" },
};

export default function MarketRegime({ sym, startdate, investment, onStrategyPick, autoRegime, onRegimeDetected }) {
  const [regime, setRegime] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState("");
  useEffect(() => {
    if (autoRegime) setRegime(autoRegime);
  }, [autoRegime]);
  
  const analyze = async () => {
    if (!sym || !startdate) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("http://localhost:8000/regime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sym, startdate, investment: parseFloat(investment) || 10000, stra: "Bollinger Band" }),
      });
      const data = await res.json();
      if (data.status === "fail") throw new Error(data.message);
      setRegime(data);
      onRegimeDetected?.(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const colors = regime ? (REGIME_COLORS[regime.regime] || REGIME_COLORS["Ranging/Sideways"]) : null;

  return (
    <div className="regime-panel">
      <h4 className="regime-title">
        MARKET REGIME
      </h4>

      <button
        className="regime-analyze-btn"
        onClick={analyze}
        disabled={loading || !sym || !startdate}
      >
        {loading ? "ANALYSING..." : "DETECT REGIME"}
      </button>

      {error && (
        <div style={{ color: "#fca5a5", fontSize: "0.72rem", marginBottom: "0.75rem" }}>⚠ {error}</div>
      )}

      {regime && (
        <div className="regime-content">
          {/* Regime badge */}
          <div className="regime-summary" style={{
            background: colors.bg, border: `1px solid ${colors.border}`,
            borderRadius: "8px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: colors.text, fontWeight: 700, fontSize: "0.85rem" }}>
                {regime.regime}
              </span>
              <span style={{
                background: colors.border + "33", color: colors.text,
                fontSize: "0.65rem", padding: "2px 8px", borderRadius: "20px"
              }}>
                {regime.confidence}% confidence
              </span>
            </div>
            <p style={{ color: "#94a3b8", fontSize: "0.7rem", marginTop: "6px", lineHeight: 1.5 }}>
              {regime.reasoning}
            </p>
          </div>

          {/* Indicator pills */}
          <div className="indicator-pills">
            {[
              ["ADX", regime.indicators.adx],
              ["RSI", regime.indicators.rsi],
              ["ATR%", regime.indicators.atr_pct],
              ["EMA Slope", regime.indicators.ema50_slope],
            ].map(([label, val]) => (
              <div key={label} style={{
                background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "6px", padding: "4px 8px", fontSize: "0.65rem", color: "#cbd5e1"
              }}>
                <span style={{ color: "#64748b" }}>{label}: </span>{val}
              </div>
            ))}
          </div>

          {/* Strategy recommendations */}
          <div className="strategy-recommendations">
            <div style={{ color: "#64748b", fontSize: "0.65rem", letterSpacing: "0.1em", marginBottom: "0.5rem" }}>
              RECOMMENDED STRATEGIES
            </div>
            <div className="strategy-pills">
            {regime.recommended_strategies.map((s) => (
              <div
                className="strategy-pill"
                key={s}
                onClick={() => onStrategyPick(s)}
                style={{
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: "8px", padding: "10px 12px", marginBottom: "6px", cursor: "pointer",
                  transition: "border-color 0.2s"
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = colors.border}
                onMouseLeave={e => e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"}
              >
                <div style={{ color: "#e2e8f0", fontSize: "0.75rem", fontWeight: 600 }}>{s}</div>
                <div style={{ color: "#64748b", fontSize: "0.65rem", marginTop: "3px", lineHeight: 1.4 }}>
                  {regime.strategy_descriptions[s]}
                </div>
                <div style={{ color: colors.text, fontSize: "0.62rem", marginTop: "4px" }}>
                  → Click to auto-select
                </div>
              </div>
            ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
