// Shared regime palette.
//
// Both the rule-based panel and the HMM panel name regimes from the same
// vocabulary (backend/market_regime.py), so they have to colour them the same
// way -- otherwise "Trending Up" looks like two different things depending on
// which panel you read.

export const REGIME_COLORS = {
  "Trending Up":      { bg: "rgba(34,197,94,0.15)",  border: "#22c55e", text: "#86efac" },
  "Trending Down":    { bg: "rgba(239,68,68,0.15)",  border: "#ef4444", text: "#fca5a5" },
  "High Volatility":  { bg: "rgba(234,179,8,0.15)",  border: "#eab308", text: "#fde047" },
  "Low Volatility":   { bg: "rgba(99,102,241,0.15)", border: "#6366f1", text: "#a5b4fc" },
  "Ranging/Sideways": { bg: "rgba(148,163,184,0.15)",border: "#94a3b8", text: "#cbd5e1" },
};

export const FALLBACK_REGIME = "Ranging/Sideways";

export function regimeColor(name) {
  return REGIME_COLORS[name] || REGIME_COLORS[FALLBACK_REGIME];
}

export default REGIME_COLORS;
