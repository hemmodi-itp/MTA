"""
tools.benchmark — MTA benchmark runner and scorer (Phase 0.2–0.4).

    python -m tools.benchmark.run --app buggy_shop

apps.py         benchmark app registry (ground truth, BRD split per module)
app_server.py   start/stop an app subprocess with chosen bug flags
materialize.py  write the generated MTA project for an app
score.py        pure metric computation
report_md.py    Markdown summary
run.py          the end-to-end CLI
"""
