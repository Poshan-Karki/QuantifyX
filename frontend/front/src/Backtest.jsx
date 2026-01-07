// Backtest.jsx
import React, { useState, useEffect } from "react";
import Chart from "./Chart";
import "./Backtest.css";

function Backtest() {
  const [message, setMessage] = useState({ summary: {}, ohlc: [], trades: [], indicators: {} });
  const [sym, setSym] = useState("");
  const [symbolList, setList] = useState([]);
  const [strategy, setStrategy] = useState("");
  const [investment, setInve] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/hydroname").then(res => res.json()).then(data => setList(data));
  }, []);

  const runBacktest = async () => {
    setLoading(true);
    const res = await fetch("http://localhost:8000/bbband", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ investement: parseFloat(investment), sym, stra: strategy }),
    });
    const data = await res.json();
    setMessage(data);
    setLoading(false);
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
          <label>Algorithm</label>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="">Choose Logic</option>
            <option value="Bollinger Band">Bollinger Band</option>
            <option value="Moving Average Crossover">MA Crossover</option>
            <option value="Mean Reversion">Mean Reversion</option>
            <option value="Bollinger+Rsi">Bollinger+Rsi</option>
          </select>
        </div>
        <div className="control-group">
          <label>Capital</label>
          <input type="number" value={investment} onChange={(e) => setInve(e.target.value)} placeholder="10000" />
        </div>
        <button className="run-btn" onClick={runBacktest} disabled={loading}>
          {loading ? "PROCESSING..." : "RUN ANALYSIS"}
        </button>
      </aside>

      <main className="dashboard-main">
        <div className="scroll-content">
          {message.ohlc.length > 0 ? (
            <>
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
        trades: message.trades // Pass the trades array here
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