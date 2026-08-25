"""Regime inference primitives, shared by the API and the offline study.

These four modules are application code. `backend/hmm_service.py` imports them,
so the forward recursion behind `/hmm` is the same tested code any study runs
against -- which is the point. Duplicating them so the two could be separated
would create two versions of the one piece that must not drift.

  features     the HMM observation frame, and the fit-on-train-only
               winsoriser/standardiser
  hmm_regime   forward recursion, canonical state ordering, BIC state selection
  rule_regime  vectorised form of market_regime.detect_regime's thresholds
  synthetic    data with a known generating process, for testing the above

They used to live in `backend/research/`, which inverted the dependency: the
application imported from a research package, so the study could not be removed
or relocated without taking the API down with it. The dependency now runs the
right way -- research imports from here, nothing here imports research.

Nothing in this package may import `research`. That boundary is what keeps the
leak the study measures out of the request path, and tests assert it.
"""
