import React, { useState, useEffect } from "react";
import Chart from "./Chart";
import "./Backtest.css";
import MarketRegime from "./MarketRegime";
import HmmRegime from "./HmmRegime";
import MarketContext from "./MarketContext";
import { apiUrl } from "./api";

function Backtest() {
  const [message, setMessage] = useState({
    summary: {},
    ohlc: [],
    trades: [],
    indicators: {},
    verdict: null,
    regime: null,
    selection_regime: null,
    evaluation: null,
    market_context: null,
    contextual_verdict: null,
  });
  const [sym, setSym] = useState("");
  const [symbolList, setList] = useState([]);
  const [symbolSearch, setSymbolSearch] = useState("");
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
    fetch(apiUrl("/hydroname")).then(res => res.json()).then(data => setList(data));
  }, []);

  useEffect(() => {
    if (autoStrategy && message?.evaluation?.selected_strategy) {
      setStrategy(message.evaluation.selected_strategy);
    }
  }, [autoStrategy, message?.evaluation?.selected_strategy]);

  useEffect(() => {
    if (autoStrategy) setStrategy("");
  }, [autoStrategy, sym, startDate]);

  const isNotRecommended =
    message?.regime &&
    !message.regime.recommended_strategies?.includes(strategy);

  const normalizedSymbolSearch = symbolSearch.trim().toLowerCase();
  const filteredSymbolList = symbolList.filter((item) =>
    String(item.Symbol).toLowerCase().includes(normalizedSymbolSearch)
  );

  const handleSymbolSearch = (value) => {
    setSymbolSearch(value);
    const exactMatch = symbolList.find(
      (item) => String(item.Symbol).toLowerCase() === value.trim().toLowerCase()
    );
    if (exactMatch) setSym(exactMatch.Symbol);
  };

  const selectFirstSearchResult = () => {
    if (filteredSymbolList.length > 0) {
      setSym(filteredSymbolList[0].Symbol);
      setSymbolSearch(filteredSymbolList[0].Symbol);
    }
  };

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    await new Promise(r => setTimeout(r, 0));
    try {
      const res = await fetch(apiUrl("/bbband"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investment: parseFloat(investment),
          sym,
          stra: autoStrategy ? "" : strategy,
          startdate: startDate,
          auto_strategy: autoStrategy,
          fee_pct: parseFloat(feePct),
          slippage_pct: parseFloat(slippagePct),
          max_pos_pct: parseFloat(maxPosPct),
          cooldown_bars: parseInt(cooldownBars, 10),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        // FastAPI returns 422 validation errors as a list of {loc, msg} objects.
        const validationMessage = Array.isArray(detail?.detail)
          ? detail.detail
              .map((d) => `${d.loc?.[d.loc.length - 1] ?? "input"}: ${d.msg}`)
              .join("; ")
          : detail?.detail;
        throw new Error(validationMessage || "Server returned an error");
      }
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
      <section className="configuration-panel">
        <div className="section-heading">
          <div>
            <span className="section-kicker">BACKTEST WORKSTATION</span>
            <h3>Strategy Configuration</h3>
          </div>
          <span className="section-hint">Configure execution parameters, then run your analysis.</span>
        </div>
        <div className="config-grid config-grid-primary">
        <div className="control-group asset-control">
          <label>Asset</label>
          <div className="asset-search">
            <span className="asset-search-icon" aria-hidden="true">⌕</span>
            <input
              type="search"
              value={symbolSearch}
              onChange={(e) => handleSymbolSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  selectFirstSearchResult();
                }
              }}
              placeholder="Search stock symbol"
              aria-label="Search stock symbols"
              list="stock-symbol-suggestions"
            />
            <datalist id="stock-symbol-suggestions">
              {filteredSymbolList.slice(0, 12).map((item) => (
                <option key={item.Symbol} value={item.Symbol} />
              ))}
            </datalist>
            {symbolSearch && (
              <button
                type="button"
                className="asset-search-clear"
                onClick={() => setSymbolSearch("")}
                aria-label="Clear stock search"
              >
                ×
              </button>
            )}
          </div>
          <select
            value={sym}
            onChange={(e) => {
              setSym(e.target.value);
              if (e.target.value) setSymbolSearch(e.target.value);
            }}
          >
            <option value="">
              {filteredSymbolList.length ? "Select Ticker" : "No matching symbols"}
            </option>
            {filteredSymbolList.map((item) => (
              <option key={item.Symbol} value={item.Symbol}>{item.Symbol}</option>
            ))}
          </select>
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
        <label className="auto-strategy-toggle">
          <input
            type="checkbox"
            checked={autoStrategy}
            onChange={(e) => setAutoStrategy(e.target.checked)}
          />
          <span>
            <strong>Auto Strategy</strong>
            <small>Select first, then test on later data</small>
          </span>
        </label>
        </div>
        <div className="config-grid config-grid-secondary">
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
        <button
          className="run-btn"
          onClick={runBacktest}
          disabled={loading || !sym || !startDate || !investment || (!autoStrategy && !strategy)}
        >
          {loading ? "PROCESSING..." : "RUN ANALYSIS"}
        </button>
        </div>
        {!autoStrategy && isNotRecommended && (
          <div className="warning-banner">
            Selected strategy is not recommended. Consider: {message?.regime?.recommended_strategies?.join(", ")}
          </div>
        )}

        <MarketRegime
          sym={sym}
          startdate={startDate}
          investment={investment}
          onStrategyPick={(s) =>{ setStrategy(s); setAutoStrategy(false);}}
          autoRegime={message.regime}
          autoStrategy={autoStrategy}
          onAutoStrategyChange={setAutoStrategy}
          onRegimeDetected={(data) => setMessage(prev => ({ ...prev, regime: data }))}
        />

        <HmmRegime
          sym={sym}
          onStrategyPick={(s) => { setStrategy(s); setAutoStrategy(false); }}
        />
      </section>

      <main className="dashboard-main">
        <div className="results-content">
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
              {message.evaluation && (
                <div className={`evaluation-banner ${message.evaluation.mode === "out_of_sample" ? "evaluation-holdout" : ""}`}>
                  <div>
                    <span className="evaluation-label">
                      {message.evaluation.mode === "out_of_sample"
                        ? "UNSEEN-PERIOD TEST"
                        : "FULL-PERIOD TEST"}
                    </span>
                    <strong>{message.evaluation.selected_strategy}</strong>
                    <small>{message.evaluation.selection_basis}</small>
                  </div>
                  <div className="evaluation-periods">
                    {message.evaluation.training_period && (
                      <span>
                        Strategy Selection Period: {message.evaluation.training_period.start} – {message.evaluation.training_period.end}
                        {" "}({message.evaluation.training_period.bars} bars)
                      </span>
                    )}
                    <span>
                      {message.evaluation.mode === "out_of_sample" ? "Testing Period" : "Period"}:
                      {" "}{message.evaluation.evaluation_period.start} – {message.evaluation.evaluation_period.end}
                      {" "}({message.evaluation.evaluation_period.bars} bars)
                    </span>
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
              {message.verdict && (
                <div className="verdict-card" style={{
                  background: message.verdict.action === "BUY" ? "rgba(34,197,94,0.15)"
                    : message.verdict.action === "AVOID" ? "rgba(239,68,68,0.15)"
                      : "rgba(234,179,8,0.15)",
                  border: `1px solid ${
                    message.verdict.action === "BUY" ? "#22c55e"
                      : message.verdict.action === "AVOID" ? "#ef4444"
                        : "#eab308"
                  }`,
                  borderRadius: "8px"
                }}>
                  <div className="verdict-label">STRATEGY VERDICT</div>
                  <div className="verdict-content">
                    <div className="verdict-action">{message.verdict.action}</div>
                    <div className="verdict-message">{message.verdict.message}</div>
                  </div>
                  <div className="verdict-disclosure">
                    Based on this strategy's backtested performance over the tested period — not a live buy/sell signal for today's price.
                  </div>
                </div>
              )}
              <MarketContext
                context={message.market_context}
                contextualVerdict={message.contextual_verdict}
              />
              <div className="chart-container">
                <Chart data={{
                  ohlc: message.ohlc,
                  indicators: message.indicators,
                  trades: message.trades
                }} />
              </div>
              <div className="table-container">
                <table>
                  <thead><tr><th>Entry Date</th><th>Type</th><th>Entry Price</th><th>Exit Date</th><th>Exit Price</th><th>PnL</th></tr></thead>
                  <tbody>
                    {message.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{t.EntryTime}</td>
                        <td className={t.Size > 0 ? "buy" : "sell"}>{t.Size > 0 ? "LONG" : "SHORT"}</td>
                        <td>{t.EntryPrice?.toFixed(2)}</td>
                        <td>{t.ExitTime}</td>
                        <td>{t.ExitPrice?.toFixed(2)}</td>
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
