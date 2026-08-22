"""Offline research harness for the regime look-ahead study.

This package is deliberately separate from the FastAPI application. The app
wants a fast, cached endpoint; the study wants a slow, seed-fixed, fully
reproducible batch job. Nothing in here is imported by main.py, and nothing in
here should ever be made to serve a request -- that is how the leak the study
measures would get reintroduced.

Run it from the backend root:

    python -m research.runner --config research/configs/baseline.yaml

See RESEARCH_DESIGN for the design this implements; section numbers referenced
in the module docstrings point back at it.
"""
