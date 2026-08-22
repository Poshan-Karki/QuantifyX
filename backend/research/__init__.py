"""Offline research harness for the regime look-ahead study.

This package is deliberately separate from the FastAPI application. The app
wants a fast, cached endpoint; the study wants a slow, seed-fixed, fully
reproducible batch job.

The boundary runs through the package, not around it:

  Shared with production. features, hmm_regime and rule_regime are inference
  primitives -- the forward recursion, canonical state ordering, BIC selection,
  the vectorised rule labels. hmm_service.py imports these. Duplicating them so
  the API could avoid the import would only create two versions to drift apart,
  and the forward recursion in particular is the one piece that must not drift.

  Study only. arms, walkforward, config, data, metrics and runner are the
  experiment. Nothing in an API path may import them, and no request may ever
  reach them -- that is how the leak the study measures would get reintroduced.

Run it from the backend root:

    python -m research.runner --config research/configs/baseline.yaml

See RESEARCH_DESIGN for the design this implements; section numbers referenced
in the module docstrings point back at it.
"""
