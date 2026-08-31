import React, { useState, useEffect } from "react";
import Chart from "./Chart";
import "./Backtest.css";
import MarketRegime from "./MarketRegime";
import HmmRegime from "./HmmRegime";
import MarketContext from "./MarketContext";
import BacktestForm from "./BacktestForm";
import { getJson, getList, postJson } from "./api";

const EMPTY_RESULT = {
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
  costs: null,
};

/** Fallback only. The real values come from GET /defaults so the form and the
 *  backend cannot disagree about what a default backtest costs. */
const FALLBACK_PARAMS = {
  feePct: "0.2",
  slippagePct: "0.1",
  maxPosPct: "20",
  cooldownBars: "3",
};

function Backtest() {
  const [message, setMessage] = useState(EMPTY_RESULT);
  const [sym, setSym] = useState("");
  const [symbolList, setList] = useState([]);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [strategy, setStrategy] = useState("");
  const [investment, setInve] = useState("");
  const [loading, setLoading] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [error, setError] = useState("");
  const [autoStrategy, setAutoStrategy] = useState(true);
  const [tradeParams, setTradeParams] = useState(FALLBACK_PARAMS);

  useEffect(() => {
    // A non-array body used to reach setList and throw inside the render below,
    // which unmounted the page. getList guarantees an array; the catch turns a
    // dead API into a message instead of a blank screen.
    getList("/hydroname")
      .then(setList)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    getJson("/defaults")
      .then((defaults) =>
        setTradeParams({
          feePct: String(defaults.fee_pct),
          slippagePct: String(defaults.slippage_pct),
          maxPosPct: String(defaults.max_pos_pct),
          cooldownBars: String(defaults.cooldown_bars),
        }),
      )
      .catch(() => {
        /* keep the fallback; the run will still send explicit values */
      });
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
    String(item.Symbol).toLowerCase().includes(normalizedSymbolSearch),
  );

  const handleSymbolSearch = (value) => {
    setSymbolSearch(value);
    const exactMatch = symbolList.find(
      (item) => String(item.Symbol).toLowerCase() === value.trim().toLowerCase(),
    );
    if (exactMatch) setSym(exactMatch.Symbol);
  };

  const selectFirstSearchResult = () => {
    if (filteredSymbolList.length > 0) {
      setSym(filteredSymbolList[0].Symbol);
      setSymbolSearch(filteredSymbolList[0].Symbol);
    }
  };

  const handleTradeParamChange = (key, value) =>
    setTradeParams((prev) => ({ ...prev, [key]: value }));

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    await new Promise((r) => setTimeout(r, 0));
    try {
      const data = await postJson("/bbband", {
        investment: parseFloat(investment),
        sym,
        stra: autoStrategy ? "" : strategy,
        startdate: startDate,
        auto_strategy: autoStrategy,
        fee_pct: parseFloat(tradeParams.feePct),
        slippage_pct: parseFloat(tradeParams.slippagePct),
        max_pos_pct: parseFloat(tradeParams.maxPosPct),
        cooldown_bars: parseInt(tradeParams.cooldownBars, 10),
      });
      setMessage(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="backtest-dashboard">
      <section className="configuration-panel">
        <BacktestForm
          symbols={filteredSymbolList}
          symbolSearch={symbolSearch}
          onSymbolSearch={handleSymbolSearch}
          onSymbolSearchEnter={selectFirstSearchResult}
          onSymbolSearchClear={() => setSymbolSearch("")}
          sym={sym}
          onSymChange={(value) => {
            setSym(value);
            if (value) setSymbolSearch(value);
          }}
          strategy={strategy}
          onStrategyChange={setStrategy}
          autoStrategy={autoStrategy}
          onAutoStrategyChange={setAutoStrategy}
          startDate={startDate}
          onStartDateChange={setStartDate}
          investment={investment}
          onInvestmentChange={setInve}
          tradeParams={tradeParams}
          onTradeParamChange={handleTradeParamChange}
          loading={loading}
          onRun={runBacktest}
        />

        {!autoStrategy && isNotRecommended && (
          <div className="warning-banner">
            Selected strategy is not recommended. Consider:{" "}
            {message?.regime?.recommended_strategies?.join(", ")}
          </div>
        )}

        <MarketRegime
          sym={sym}
          startdate={startDate}
          onStrategyPick={(s) => {
            setStrategy(s);
            setAutoStrategy(false);
          }}
          autoRegime={message.regime}
          autoStrategy={autoStrategy}
          onAutoStrategyChange={setAutoStrategy}
          onRegimeDetected={(data) =>
            setMessage((prev) => ({ ...prev, regime: data }))
          }
        />

        <HmmRegime
          sym={sym}
          onStrategyPick={(s) => {
            setStrategy(s);
            setAutoStrategy(false);
          }}
        />
      </section>

      <main className="dashboard-main">
        <div className="results-content">
          {loading && (
            <div style={{ display: "flex", gap: "12px", marginBottom: "1rem" }}>
              {[...Array(4)].map((_, i) => (
                <div
                  key={i}
                  className="skeleton"
                  style={{ height: "72px", flex: 1, borderRadius: "8px" }}
                />
              ))}
            </div>
          )}
          {loading && (
            <div className="skeleton" style={{ height: "380px", borderRadius: "12px" }} />
          )}
          {error && (
            <div className="results-error" role="alert">
              ⚠ {error}
            </div>
          )}
          {message.ohlc.length > 0 ? (
            <>
              {message.evaluation && (
                <div
                  className={`evaluation-banner ${
                    message.evaluation.mode === "out_of_sample"
                      ? "evaluation-holdout"
                      : ""
                  }`}
                >
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
                        Strategy Selection Period:{" "}
                        {message.evaluation.training_period.start} –{" "}
                        {message.evaluation.training_period.end} (
                        {message.evaluation.training_period.bars} bars)
                      </span>
                    )}
                    <span>
                      {message.evaluation.mode === "out_of_sample"
                        ? "Testing Period"
                        : "Period"}
                      : {message.evaluation.evaluation_period.start} –{" "}
                      {message.evaluation.evaluation_period.end} (
                      {message.evaluation.evaluation_period.bars} bars)
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
              {message.costs && (
                <p className="cost-applied">
                  Costs applied: {message.costs.fee_pct}% fee +{" "}
                  {message.costs.slippage_pct}% slippage ={" "}
                  {message.costs.total_cost_pct.toFixed(2)}% each way.{" "}
                  {message.costs.basis}
                </p>
              )}
              {message.verdict && (
                <div
                  className="verdict-card"
                  style={{
                    background:
                      message.verdict.action === "BUY"
                        ? "rgba(34,197,94,0.15)"
                        : message.verdict.action === "AVOID"
                          ? "rgba(239,68,68,0.15)"
                          : "rgba(234,179,8,0.15)",
                    border: `1px solid ${
                      message.verdict.action === "BUY"
                        ? "#22c55e"
                        : message.verdict.action === "AVOID"
                          ? "#ef4444"
                          : "#eab308"
                    }`,
                    borderRadius: "8px",
                  }}
                >
                  <div className="verdict-label">STRATEGY VERDICT</div>
                  <div className="verdict-content">
                    <div className="verdict-action">{message.verdict.action}</div>
                    <div className="verdict-message">{message.verdict.message}</div>
                  </div>
                  <div className="verdict-disclosure">
                    Based on this strategy's backtested performance over the tested
                    period — not a live buy/sell signal for today's price. Prices are
                    not adjusted for bonus issues, splits or rights, so returns
                    spanning a corporate action will be wrong.
                  </div>
                </div>
              )}
              <MarketContext
                context={message.market_context}
                contextualVerdict={message.contextual_verdict}
              />
              <div className="chart-container">
                <Chart
                  data={{
                    ohlc: message.ohlc,
                    indicators: message.indicators,
                    trades: message.trades,
                  }}
                />
              </div>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Entry Date</th>
                      <th>Type</th>
                      <th>Entry Price</th>
                      <th>Exit Date</th>
                      <th>Exit Price</th>
                      <th>PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {message.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{t.EntryTime}</td>
                        <td className={t.Size > 0 ? "buy" : "sell"}>
                          {t.Size > 0 ? "LONG" : "SHORT"}
                        </td>
                        <td>{t.EntryPrice?.toFixed(2)}</td>
                        <td>{t.ExitTime}</td>
                        <td>{t.ExitPrice?.toFixed(2)}</td>
                        <td className={t.PnL > 0 ? "buy" : "sell"}>
                          {t.PnL?.toFixed(2)}
                        </td>
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
