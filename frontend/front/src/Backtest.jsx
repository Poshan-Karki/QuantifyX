import React, { useState, useEffect } from "react";
import Chart from "./Chart";
import "./Backtest.css";
import MarketRegime from "./MarketRegime";

function Backtest() {
  const [message, setMessage] = useState({ summary: {}, ohlc: [], trades: [], indicators: {}, verdict: null, regime: null });
  const [sym, setSym] = useState("");
  const [symbolList, setList] = useState([]);
  const [strategy, setStrategy] = useState("");
  const [investment, setInve] = useState("");
  const [loading, setLoading] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [error, setError] = useState("");
  const [autoStrategy, setAutoStrategy] = useState(true);
  const [feePct, setFeePct] = useState("0.1");
  const [slippagePct, setSlippagePct] = useState("0.05");
  const [maxPosPct, setMaxPosPct] = useState("100");
  const [cooldownBars, setCooldownBars] = useState("0");

  useEffect(() => {
    fetch("http://localhost:8000/hydroname").then(res => res.json()).then(data => setList(data));
  }, []);

  useEffect(() => {
    if (autoStrategy && message?.regime?.recommended_strategies?.length) {
      setStrategy(message.regime.recommended_strategies[0]);
    }
  }, [autoStrategy, message?.regime]);

  const isNotRecommended =
    message?.regime &&
    !message.regime.recommended_strategies?.includes(strategy);

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    await new Promise(r => setTimeout(r, 0));
    try {
      const res = await fetch("http://localhost:8000/bbband", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investment: parseFloat(investment),
          sym,
          stra: strategy,
          startdate: startDate,
          fee_pct: parseFloat(feePct),
          slippage_pct: parseFloat(slippagePct),
          max_pos_pct: parseFloat(maxPosPct),
          cooldown_bars: parseInt(cooldownBars, 10),
        }),
      });
      if (!res.ok) throw new Error("Server returned an error");
      const data = await res.json();
      if (data.status === "fail") {
        throw new Error(data.message);
      }
      setMessage(data);
    }
    catch (err) {
      setError(err.message);
    }
    finally {
      setLoading(false);
    }
  };

  return (
    <div className="backtest-dashboard">
      <aside className="dashboard-sidebar">
        <h3 className="sidebar-title">Strategy Config</h3>
        <div className="control-group">
          <label>Asset</label>
          <select value={sym} onChange={(e) => setSym(e.target.value)}>
            <option value="">Select Ticker</option>
            {symbolList.map((item, i) => <option key={i} value={item.Symbol}>{item.Symbol}</option>)}
          </select>
        </div>
        <div className="control-group">
          <label>
            <input
              type="checkbox"
              checked={autoStrategy}
              onChange={(e) => setAutoStrategy(e.target.checked)}
            />
            {" "}Auto-select strategy from market regime
          </label>
        </div>
        <div className="control-group">
          <label>Algorithm</label>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)} disabled={autoStrategy}>
            <option value="">Choose Logic</option>
            <option value="Bollinger Band">Bollinger Band</option>
            <option value="Moving Average Crossover">MA Crossover</option>
            <option value="Mean Reversion">Mean Reversion</option>
            <option value="Bollinger+Rsi">BollingerRsi</option>
            <option value="VolumeBreakout">VolumeBreakout</option>
            <option value="MACD Cross">MACD Cross</option>
            <option value="RSI Mean Reversion">RSI Mean Reversion</option>
            <option value="ATR Breakout">ATR Breakout</option>
          </select>
        </div>
        {!autoStrategy && isNotRecommended && (
          <div className="warning-banner">
            Selected strategy is not recommended. Consider: {message?.regime?.recommended_strategies?.join(", ")}
          </div>
        )}
        <div className="control-group">
          <label>Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>

        <div className="control-group">
          <label>Capital</label>
          <input type="number" value={investment} onChange={(e) => setInve(e.target.value)} placeholder="10000" />
        </div>
        <div className="control-group">
          <label>Fee (%)</label>
          <input type="number" step="0.01" value={feePct} onChange={(e) => setFeePct(e.target.value)} />
        </div>
        <div className="control-group">
          <label>Slippage (%)</label>
          <input type="number" step="0.01" value={slippagePct} onChange={(e) => setSlippagePct(e.target.value)} />
        </div>
        <div className="control-group">
          <label>Max Position (%)</label>
          <input type="number" step="1" value={maxPosPct} onChange={(e) => setMaxPosPct(e.target.value)} />
        </div>
        <div className="control-group">
          <label>Cooldown (bars)</label>
          <input type="number" step="1" value={cooldownBars} onChange={(e) => setCooldownBars(e.target.value)} />
        </div>
        <button className="run-btn" onClick={runBacktest} disabled={loading}>
          {loading ? "PROCESSING..." : "RUN ANALYSIS"}
        </button>
        <MarketRegime
          sym={sym}
          startdate={startDate}
          investment={investment}
          onStrategyPick={(s) =>{ setStrategy(s); setAutoStrategy(false);}}
          autoRegime={message.regime}
          onRegimeDetected={(data) => setMessage(prev => ({ ...prev, regime: data }))}
        />
      </aside>

      <main className="dashboard-main">
        <div className="scroll-content">
          {loading && (
            <div style={{ display: "flex", gap: "12px", marginBottom: "1rem" }}>
              {[...Array(4)].map((_, i) => (
                <div key={i} className="skeleton" style={{ height: "72px", flex: 1, borderRadius: "8px" }} />
              ))}
            </div>
          )}
          {loading && (
            <div className="skeleton" style={{ height: "380px", borderRadius: "12px" }} />
          )}
          {error && (
            <div style={{
              background: "rgba(220, 38, 38, 0.15)",
              color: "#fca5a5",
              padding: "12px 16px",
              borderRadius: "8px",
              marginBottom: "1rem"
            }}>
              ⚠ {error}
            </div>
          )}
          {message.ohlc.length > 0 ? (
            <>
              {message.verdict && (
                <div style={{
                  background: message.verdict.action === "BUY" ? "rgba(34,197,94,0.15)"
                    : message.verdict.action === "AVOID" ? "rgba(239,68,68,0.15)"
                      : "rgba(234,179,8,0.15)",
                  border: `1px solid ${
                    message.verdict.action === "BUY" ? "#22c55e"
                      : message.verdict.action === "AVOID" ? "#ef4444"
                        : "#eab308"
                  }`,
                  borderRadius: "8px",
                  padding: "14px 16px",
                  marginBottom: "1rem"
                }}>
                  <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "4px" }}>
                    {message.verdict.action}
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "#cbd5e1", lineHeight: 1.5 }}>
                    {message.verdict.message}
                  </div>
                </div>
              )}
              <div className="metrics-row">
                {Object.entries(message.summary).map(([key, val]) => (
                  <div key={key} className="metric-box">
                    <div className="metric-label">{key}</div>
                    <div className="metric-value">{val}</div>
                  </div>
                ))}
              </div>
              <div className="chart-container">
                <Chart data={{
                  ohlc: message.ohlc,
                  indicators: message.indicators,
                  trades: message.trades
                }} />
              </div>
              <div className="table-container">
                <table>
                  <thead><tr><th>Time</th><th>Type</th><th>Price</th><th>PnL</th></tr></thead>
                  <tbody>
                    {message.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{t.EntryTime}</td>
                        <td className={t.Size > 0 ? "buy" : "sell"}>{t.Size > 0 ? "LONG" : "SHORT"}</td>
                        <td>{t.EntryPrice?.toFixed(2)}</td>
                        <td className={t.PnL > 0 ? "buy" : "sell"}>{t.PnL?.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty-msg">Ready for strategy initialization.</div>
          )}
        </div>
      </main>
    </div>
  );
}
export default Backtest;
