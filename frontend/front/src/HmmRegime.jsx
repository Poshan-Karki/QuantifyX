import React, { useState } from "react";
import { apiUrl } from "./api";
import { regimeColor } from "./regimeColors";

// Collapse the per-bar label series into runs, so the timeline draws one block
// per stretch of a regime rather than 250 slivers. The run length is what a
// reader actually wants to see -- how long the market stayed in each state.
function toRuns(dates, labels) {
  const runs = [];
  for (let i = 0; i < labels.length; i++) {
    const last = runs[runs.length - 1];
    if (last && last.label === labels[i]) {
      last.bars += 1;
      last.end = dates[i];
    } else {
      runs.push({ label: labels[i], bars: 1, start: dates[i], end: dates[i] });
    }
  }
  return runs;
}

function Pct({ value }) {
  return <>{(value * 100).toFixed(0)}%</>;
}

export default function HmmRegime({ sym, onStrategyPick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const detect = async () => {
    if (!sym) return;
    setLoading(true);
    setError("");
    try {
      // No startdate on purpose: the model wants every bar it can get, and the
      // backtest window the user picked is often far too short to fit on.
      const res = await fetch(apiUrl("/hmm"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sym }),
      });
      const payload = await res.json();
      if (payload.status === "fail") throw new Error(payload.message);
      setData(payload);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const colors = data ? regimeColor(data.regime) : null;
  const runs = data ? toRuns(data.history.dates, data.history.labels) : [];
  const legend = data ? [...new Set(data.history.labels)] : [];

  return (
    <div className="regime-panel hmm-panel">
      <h4 className="regime-title">
        HMM REGIME
        <span className="hmm-subtitle">hidden markov</span>
      </h4>

      <button className="regime-analyze-btn hmm-btn" onClick={detect} disabled={loading || !sym}>
        {loading ? "FITTING..." : "DETECT WITH HMM"}
      </button>

      {error && <div className="hmm-error">⚠ {error}</div>}

      {data && (
        <div className="regime-content hmm-content">
          {/* Current regime and what it expects next */}
          <div
            className="regime-summary"
            style={{ background: colors.bg, border: `1px solid ${colors.border}`, borderRadius: "8px" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: colors.text, fontWeight: 700, fontSize: "0.85rem" }}>
                {data.regime}
              </span>
              <span
                style={{
                  background: colors.border + "33",
                  color: colors.text,
                  fontSize: "0.65rem",
                  padding: "2px 8px",
                  borderRadius: "20px",
                }}
              >
                <Pct value={data.confidence} /> confidence
              </span>
            </div>

            <div className="hmm-forecast">
              {data.regime_change_expected ? (
                <>
                  <span style={{ color: "#fde047" }}>▸ shift expected</span> to{" "}
                  <span style={{ color: regimeColor(data.next_regime).text }}>{data.next_regime}</span>{" "}
                  (<Pct value={data.next_regime_probability} />)
                </>
              ) : (
                <>
                  <span style={{ color: "#86efac" }}>▸ no shift expected</span> — likely still{" "}
                  <span style={{ color: colors.text }}>{data.next_regime}</span> (
                  <Pct value={data.next_regime_probability} />)
                </>
              )}
            </div>

            <p style={{ color: "#94a3b8", fontSize: "0.68rem", marginTop: "6px", lineHeight: 1.5 }}>
              {data.reasoning}
            </p>
          </div>

          {/* Per-state profile: what each hidden state actually looks like */}
          <div className="hmm-states">
            <div className="hmm-section-label">
              {data.n_states} STATES · BIC SELECTED
            </div>
            {data.states.map((s) => {
              const c = regimeColor(s.label);
              const active = s.state === data.state;
              return (
                <div
                  key={s.state}
                  className={`hmm-state-row${active ? " is-active" : ""}`}
                  style={active ? { borderColor: c.border, background: c.bg } : undefined}
                  title={`State ${s.state} covers ${(s.share_of_history * 100).toFixed(0)}% of history`}
                >
                  <span className="hmm-state-dot" style={{ background: c.border }} />
                  <span className="hmm-state-name" style={{ color: active ? c.text : "#94a3b8" }}>
                    {s.label}
                  </span>
                  <span className="hmm-state-stat" title="mean daily return">
                    {s.mean_daily_return_pct >= 0 ? "+" : ""}
                    {s.mean_daily_return_pct.toFixed(2)}%
                  </span>
                  <span className="hmm-state-stat" title="daily volatility">
                    σ {s.volatility_pct.toFixed(2)}%
                  </span>
                  <span className="hmm-state-stat" title="probability of staying in this state">
                    hold {(s.persistence * 100).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>

          {/* Strategy recommendations, same contract as the rule-based panel */}
          <div className="strategy-recommendations">
            <div className="hmm-section-label">RECOMMENDED STRATEGIES</div>
            <div className="strategy-pills">
              {data.recommended_strategies.map((s) => (
                <div
                  className="strategy-pill"
                  key={s}
                  onClick={() => onStrategyPick?.(s)}
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = colors.border)}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)")}
                >
                  <div style={{ color: "#e2e8f0", fontSize: "0.75rem", fontWeight: 600 }}>{s}</div>
                  <div style={{ color: "#64748b", fontSize: "0.65rem", marginTop: "3px" }}>
                    {data.strategy_descriptions[s]}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Regime history -- the thing the rule-based panel cannot show */}
          <div className="hmm-timeline-wrap">
            <div className="hmm-section-label">
              REGIME HISTORY
              <span className="hmm-meta">
                last {data.history.bars} bars · to {data.as_of} · filtered
              </span>
            </div>

            <div className="hmm-timeline" role="img" aria-label="Regime over time">
              {runs.map((run, i) => (
                <div
                  key={i}
                  className="hmm-segment"
                  style={{ flexGrow: run.bars, background: regimeColor(run.label).border }}
                  title={`${run.label} — ${run.bars} bar${run.bars === 1 ? "" : "s"} (${run.start} → ${run.end})`}
                />
              ))}
            </div>

            <div className="hmm-legend">
              {legend.map((name) => (
                <span key={name} className="hmm-legend-item">
                  <span className="hmm-state-dot" style={{ background: regimeColor(name).border }} />
                  {name}
                </span>
              ))}
            </div>

            <div className="hmm-note">
              Each label uses only that bar and earlier ones, so it is what the model would
              have known at the time.
              {data.model.cached && " · cached"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
