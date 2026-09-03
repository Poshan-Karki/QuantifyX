"""Offline research harness for the regime look-ahead study.

Deliberately separate from the FastAPI application. The app wants a fast, cached
endpoint; the study wants a slow, seed-fixed, fully reproducible batch job.
Making one serve both is how the leak being measured gets reintroduced.

The dependency runs one way only:

    research  ->  regime, costs, Backtest        (allowed, and used)
    app       ->  research                       (never; tests assert it)

The inference primitives both sides share -- the forward recursion, canonical
state ordering, BIC selection, the vectorised rule labels -- live in
`backend/regime/`, not here. They used to live in this package, which inverted
the dependency: `hmm_service.py` imported from a research package, so the study
could not be removed or relocated without taking the whole API down with it.

What remains here is the experiment itself:

    arms         the six arms and the strategy-selection rule
    walkforward  fold generation
    config       one reproducible run, hashed onto every output row
    data         snapshot loading and the Phase 0 audit
    execution    running strategies over bar ranges, with a per-fold cache
    metrics      Sharpe, drawdown, deflated Sharpe, stationary bootstrap
    runner       the batch job
    tests/       including the leakage assertions

Nothing in an API path may import any of it, and no request may ever reach it.

Run it from the backend root:

    python -m research.runner --config research/configs/baseline.yaml
    python -m pytest research/tests -q

See RESEARCH_DESIGN for the design this implements; section numbers referenced
in the module docstrings point back at it.
"""
