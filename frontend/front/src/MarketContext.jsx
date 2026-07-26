import React from "react";


const IMPACT_CLASS = {
  HIGH: "context-impact-high",
  MEDIUM: "context-impact-medium",
  LOW: "context-impact-low",
};

function MarketContext({ context, contextualVerdict }) {
  if (!context) return null;

  const items = context.items || [];

  return (
    <section className="market-context" aria-labelledby="market-context-title">
      <div className="market-context-heading">
        <div>
          <span className="context-kicker">DEVELOPER REVIEWED</span>
          <h3 id="market-context-title">Nepal Market Context</h3>
        </div>
        <div className="context-as-of">
          <span>AS OF {context.as_of}</span>
          <small>MARKET + {context.symbol}</small>
        </div>
      </div>

      {items.length === 0 ? (
        <div className={`context-empty context-${context.status}`}>
          {context.message}
        </div>
      ) : (
        <div className="context-items">
          {items.map((item) => (
            <article className="context-notice" key={item.id}>
              <div className="context-notice-topline">
                <div className="context-badges">
                  <span className="context-scope">
                    {item.scope === "MARKET" ? "MARKET-WIDE" : item.symbol}
                  </span>
                  <span className={IMPACT_CLASS[item.impact] || IMPACT_CLASS.MEDIUM}>
                    {item.impact} IMPACT
                  </span>
                </div>
                <time dateTime={item.published_at}>{item.published_at}</time>
              </div>

              <h4>{item.headline}</h4>
              <p>{item.message}</p>

              <div className="context-notice-meta">
                {item.source_url && (
                  <a href={item.source_url} target="_blank" rel="noreferrer">
                    {item.source_label || "View source"}
                  </a>
                )}
                {item.reviewed_by && <span>Reviewed by {item.reviewed_by}</span>}
                {item.expires_at && <span>Valid until {item.expires_at}</span>}
              </div>
            </article>
          ))}
        </div>
      )}

      {contextualVerdict && (
        <div className="contextual-verdict">
          <div className="contextual-verdict-topline">
            <span>CONTEXT-AWARE VERDICT</span>
            <small>
              Technical result: {contextualVerdict.technical_action}
            </small>
          </div>
          <strong>{contextualVerdict.label}</strong>
          <p>{contextualVerdict.message}</p>
          <small className="context-disclosure">
            {contextualVerdict.disclosure}
          </small>
        </div>
      )}
    </section>
  );
}

export default MarketContext;
