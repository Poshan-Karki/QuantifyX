import React from "react";

const STRATEGY_OPTIONS = [
  { value: "Bollinger Band", label: "Bollinger Band" },
  { value: "Moving Average Crossover", label: "MA Crossover" },
  { value: "Mean Reversion", label: "Mean Reversion" },
  { value: "Bollinger+Rsi", label: "BollingerRsi" },
  { value: "VolumeBreakout", label: "VolumeBreakout" },
  { value: "MACD Cross", label: "MACD Cross" },
  { value: "RSI Mean Reversion", label: "RSI Mean Reversion" },
  { value: "ATR Breakout", label: "ATR Breakout" },
];

const TRADE_PARAM_FIELDS = [
  { key: "feePct", label: "Fee (%)", step: "0.01" },
  { key: "slippagePct", label: "Slippage (%)", step: "0.01" },
  { key: "maxPosPct", label: "Max Position (%)", step: "1" },
  { key: "cooldownBars", label: "Cooldown (bars)", step: "1" },
];

/**
 * The strategy configuration panel.
 *
 * Split out of Backtest so that component is left holding state and data
 * fetching rather than three hundred lines of markup as well.
 */
function BacktestForm({
  symbols,
  symbolSearch,
  onSymbolSearch,
  onSymbolSearchEnter,
  onSymbolSearchClear,
  sym,
  onSymChange,
  strategy,
  onStrategyChange,
  autoStrategy,
  onAutoStrategyChange,
  startDate,
  onStartDateChange,
  investment,
  onInvestmentChange,
  tradeParams,
  onTradeParamChange,
  loading,
  onRun,
}) {
  const canRun =
    !loading && sym && startDate && investment && (autoStrategy || strategy);

  return (
    <>
      <div className="section-heading">
        <div>
          <span className="section-kicker">BACKTEST WORKSTATION</span>
          <h3>Strategy Configuration</h3>
        </div>
        <span className="section-hint">
          Configure execution parameters, then run your analysis.
        </span>
      </div>

      <div className="config-grid config-grid-primary">
        <div className="control-group asset-control">
          <label>Asset</label>
          <div className="asset-search">
            <span className="asset-search-icon" aria-hidden="true">⌕</span>
            <input
              type="search"
              value={symbolSearch}
              onChange={(e) => onSymbolSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSymbolSearchEnter();
                }
              }}
              placeholder="Search stock symbol"
              aria-label="Search stock symbols"
              list="stock-symbol-suggestions"
            />
            <datalist id="stock-symbol-suggestions">
              {symbols.slice(0, 12).map((item) => (
                <option key={item.Symbol} value={item.Symbol} />
              ))}
            </datalist>
            {symbolSearch && (
              <button
                type="button"
                className="asset-search-clear"
                onClick={onSymbolSearchClear}
                aria-label="Clear stock search"
              >
                ×
              </button>
            )}
          </div>
          <select value={sym} onChange={(e) => onSymChange(e.target.value)}>
            <option value="">
              {symbols.length ? "Select Ticker" : "No matching symbols"}
            </option>
            {symbols.map((item) => (
              <option key={item.Symbol} value={item.Symbol}>
                {item.Symbol}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Algorithm</label>
          <select
            value={strategy}
            onChange={(e) => onStrategyChange(e.target.value)}
            disabled={autoStrategy}
          >
            <option value="">Choose Logic</option>
            {STRATEGY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => onStartDateChange(e.target.value)}
          />
        </div>

        <div className="control-group">
          <label>Capital</label>
          <input
            type="number"
            value={investment}
            onChange={(e) => onInvestmentChange(e.target.value)}
            placeholder="10000"
          />
        </div>

        <label className="auto-strategy-toggle">
          <input
            type="checkbox"
            checked={autoStrategy}
            onChange={(e) => onAutoStrategyChange(e.target.checked)}
          />
          <span>
            <strong>Auto Strategy</strong>
            <small>Select first, then test on later data</small>
          </span>
        </label>
      </div>

      <div className="config-grid config-grid-secondary">
        {TRADE_PARAM_FIELDS.map((field) => (
          <div className="control-group" key={field.key}>
            <label htmlFor={`param-${field.key}`}>{field.label}</label>
            <input
              id={`param-${field.key}`}
              type="number"
              step={field.step}
              value={tradeParams[field.key]}
              onChange={(e) => onTradeParamChange(field.key, e.target.value)}
            />
          </div>
        ))}

        <button className="run-btn" onClick={onRun} disabled={!canRun}>
          {loading ? "PROCESSING..." : "RUN ANALYSIS"}
        </button>
      </div>

      <p className="cost-note">
        Fee and slippage are charged together on entry and again on exit. Entries
        fill at the next bar's open.
      </p>
    </>
  );
}

export default BacktestForm;
