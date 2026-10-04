"""
trace — Requirement Traceability Engine (deterministic parts; the LLM verifier lives in
agents/evaluation/requirement_traceability and calls into these).

  retrieve.py   hybrid retrieval: BM25 over code chunks + graph seeds, RRF-merged, graph-expanded
  citations.py  validate a verifier's citations against the checkout; prove wiring (E3 vs E2)
  decide.py     evidence ladder, verdict rules, requirement roll-up
"""
