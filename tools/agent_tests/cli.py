"""
cli.py — python -m tools.agent_tests <command>   (Phase 9.2 dataset workflow + runner + benchmark)

  generate --agent A [--seed N]                     spec + catalogs → eval_sets/A/*.jsonl (keeps human review)
  list     --agent A [--dimension D] [--unreviewed] [--ac AC-01.1]
  review   --agent A (--ids ID … | --dimension D | --all) --by NAME
  validate --agent A                                exit 1 on any error
  run      --agent A --url URL [--judge] [--k N] [--workers N] [--dimension D …] [--canary-sys TOKEN] [--out F]
  bench    [--seed 7] [--in-process] [--weakness BOT_BUG_01 …] [--repeat N] [--llm --bot-model M] [--no-write]
  calibrate export --agent A --from result.json … [--out sheet.csv]  |  calibrate compute --agent A --labels sheet.csv
  draft    --agent A --brd FILE [--requirements reqs.json]
"""

import argparse
import datetime as _dt
import json
import os
import sys
import uuid
from typing import List, Optional

from tools.agent_tests import dataset
from tools.agent_tests.catalogs import load_catalogs, versions
from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.generators import generate_all
from tools.agent_tests.models import DIMENSIONS


def _out(msg: str = "") -> None:
    print(msg, flush=True)


def cmd_generate(a) -> int:
    d = dataset.agent_dir(a.agent, a.root)
    spec = dataset.spec_for(d)
    catalogs = load_catalogs()
    results = generate_all(spec, catalogs, a.seed)
    generated = [c for r in results.values() for c in r.cases]
    existing, rep = dataset.load_cases(d)
    if rep.errors:
        _out("Existing dataset has errors; fix them first:\n  " + "\n  ".join(rep.errors))
        return 1
    merged, changes = dataset.merge(existing, generated)
    manifest = dataset.write(d, merged, spec.agent, a.seed, versions(catalogs))
    _out(f"{spec.agent}: dataset v{manifest['dataset_version']} · {manifest['total']} cases "
         f"({manifest['unreviewed']} unreviewed) → {d}")
    _out(f"{'dimension':<26}{'cases':>6}{'min':>6}")
    for dim in DIMENSIONS:
        n = manifest["counts"].get(dim, 0)
        _out(f"{dim:<26}{n:>6}{MIN_CASES[dim]:>6}{'  ← below minimum' if n < MIN_CASES[dim] else ''}")
    for k, ids in changes.items():
        if ids and k != "unchanged":
            _out(f"  {k}: {len(ids)}")
    cuts = [c for r in results.values() for c in r.cut]
    if cuts:
        _out("Not generated / short (reason):")
        for c in cuts:
            _out(f"  - {c['dimension']}: {c['reason']} — {c['detail']}")
    return 0


def cmd_list(a) -> int:
    cases, rep = dataset.load_cases(dataset.agent_dir(a.agent, a.root))
    for c in cases:
        if a.dimension and c.dimension != a.dimension:
            continue
        if a.unreviewed and c.reviewed:
            continue
        if a.ac and a.ac not in c.ac_ids:
            continue
        _out(f"{c.id}  {c.dimension:<26} {'✓' if c.reviewed else '·'} {c.source:<9} {','.join(c.ac_ids):<22} {c.title}")
    for e in rep.errors:
        _out(f"ERROR {e}")
    return 1 if rep.errors else 0


def cmd_review(a) -> int:
    if not (a.ids or a.dimension or a.all):
        _out("Choose what to mark: --ids, --dimension or --all")
        return 2
    marked, unknown = dataset.mark_reviewed(dataset.agent_dir(a.agent, a.root), a.by,
                                            _dt.date.today().isoformat(), a.ids, a.dimension, a.all)
    _out(f"Marked {len(marked)} case(s) reviewed by {a.by}.")
    if unknown:
        _out(f"Unknown ids: {', '.join(unknown)}")
        return 1
    return 0


def cmd_validate(a) -> int:
    rep = dataset.validate(dataset.agent_dir(a.agent, a.root))
    for e in rep.errors:
        _out(f"ERROR   {e}")
    for w in rep.warnings:
        _out(f"WARNING {w}")
    _out(f"{sum(rep.counts.values())} cases, {rep.unreviewed} unreviewed - {'OK' if rep.ok else 'INVALID'}")
    return 0 if rep.ok else 1


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(dataset.REPO_ROOT, ".env"))  # GOOGLE_API_KEY for the judge / drafter
    except ImportError:
        pass


def make_judge(spec, directory: str):
    from tools.agent_tests.calibration import Calibration
    from tools.agent_tests.judge import Judge
    from tools.agent_tests.llm import make_llm
    _load_env()
    return Judge(make_llm(spec.judge.connector, spec.judge.model), Calibration.load(directory),
                 agent_model=spec.agent_model, escalate=spec.judge.escalate)


def cmd_run(a) -> int:
    from tools.agent_eval.net_guard import BlockedTarget, check_target
    from tools.agent_tests import regression
    from tools.agent_tests.canaries import RunTokens
    from tools.agent_tests.judge import JudgeModelConflict
    from tools.agent_tests.runner import run_suite
    from tools.agent_tests.transport import HttpTransport

    d = dataset.agent_dir(a.agent, a.root)
    spec = dataset.spec_for(d)
    if not spec.enabled:
        _out(f"{spec.agent}: agent.yaml has enabled: false - nothing to run")
        return 0
    try:
        check_target(a.url)  # public hosts only (AQP_ALLOW_PRIVATE_TARGETS=1 for an agent on this machine)
    except BlockedTarget as exc:
        _out(f"Refused: {exc}")
        return 2
    cases, rep = dataset.load_cases(d)
    if rep.errors:
        _out("Dataset has errors; run validate.")
        return 1
    try:
        judge = make_judge(spec, d) if a.judge else None
    except JudgeModelConflict as exc:
        _out(f"Refused: {exc}")
        return 2
    run_id = a.run_id or f"run-{uuid.uuid4().hex[:12]}"
    sys_canary = a.canary_sys or spec.canaries.system_prompt_value
    tokens = RunTokens.derive(a.seed, run_id, system_canary=sys_canary).as_dict()
    if spec.canaries.system_prompt_env and not sys_canary:
        _out(f"Note: start the agent with {spec.canaries.system_prompt_env}=<token> and pass --canary-sys <token> to "
             "test system-prompt leakage; without it those checks are not_applicable.")
    result = run_suite(spec, cases, HttpTransport(a.url, spec.transport), tokens, run_id, k=a.k,
                       dimensions=a.dimension, emit=_out, judge=judge, workers=a.workers)
    if not a.no_history:
        path = regression.history_path(spec.agent, a.history_dir)
        manifest = dataset.read_manifest(d) or {}
        entry = regression.history_entry(result, manifest.get("dataset_version"), _dt.date.today().isoformat())
        result["regression"] = regression.compare(entry, regression.last_entry(path),
                                                  spec.regression.max_drop_points)
        regression.append(path, entry)
    _summary(result)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        _out(f"Wrote {a.out}")
    return 0


def _summary(result) -> None:
    _out(f"{'dimension':<26}{'defects':<17}{'gate':<21}{'pass rate':>10}{'95% CI':>13}{'n':>5}{'unverif.':>9}")
    for dim, v in result["dimensions"].items():
        st = v.get("stats") or {}
        ci = f"{st['ci_low']:.2f}-{st['ci_high']:.2f}" if st.get("ci_low") is not None else "-"
        rate = f"{st['pass_rate']:.2f}" if st.get("pass_rate") is not None else "-"
        _out(f"{dim:<26}{v['outcome']:<17}{v['verdict']:<21}{rate:>10}{ci:>13}{st.get('n') or 0:>5}"
             f"{v.get('unverified_judge_runs', 0):>9}")
    if result["cut"]:
        _out(f"{len(result['cut'])} case(s) not run: " +
             ", ".join(sorted({c['reason'] for c in result['cut']})))
    reg = result.get("regression")
    if reg:
        if reg.get("baseline"):
            _out("Regression: first recorded run of this agent")
        else:
            _out("Regression: " + ("none" if reg["ok"] else ", ".join(
                f"{r['dimension']} {r['delta_points']} pts" for r in reg["regressions"])))


def cmd_bench(a) -> int:
    from tools.agent_tests import bench
    if a.llm:
        report = bench.run_bench_llm(seed=a.seed, only=a.weakness, repeat=a.repeat or 3, bot_model=a.bot_model,
                                     workers=a.workers, k=a.k, root=a.root, emit=_out)
        md = bench.markdown_llm(report)
        label = a.label if a.label != "phase9" else "phase9_llm"
    else:
        report = bench.run_bench(seed=a.seed, in_process=a.in_process, only=a.weakness, repeat=a.repeat or 1,
                                 root=a.root, emit=_out)
        md, label = bench.markdown(report), a.label
    _out("")
    _out(md)
    if not a.no_write:
        for p in bench.write_report(report, label=label, md=md):
            _out(f"Wrote {p}")
    if a.llm:
        return 0
    s = report["summary"]
    ok = s["detected"] == s["total"] and not s["baseline_false_positives"] and s["deterministic"]
    return 0 if ok else 1


def cmd_calibrate(a) -> int:
    from tools.agent_tests import calibration
    d = dataset.agent_dir(a.agent, a.root)
    if a.action == "export":
        results = []
        for path in a.from_:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            results += list(data["runs"].values()) if isinstance(data.get("runs"), dict) else [data]
        written, available = calibration.export_sheet(results, a.out, a.target, a.seed)
        _out(f"Wrote {written} item(s) to label ({available} judged runs available) -> {a.out}")
        if written < calibration.CALIBRATION["min_items"]:
            _out(f"Note: fewer than {calibration.CALIBRATION['min_items']} items; run more judged cases first.")
        return 0
    if not a.labels:
        _out("compute needs --labels <labelled CSV>")
        return 2
    report = calibration.compute(calibration.read_labels(a.labels))
    spec = dataset.spec_for(d)
    path = calibration.save(d, report, a.judge_model or spec.judge.model)
    _out(f"{'dimension':<26}{'n':>5}{'agreement':>11}{'kappa':>8}  status")
    for dim, v in report["dimensions"].items():
        kappa = "-" if v["kappa"] is None else f"{v['kappa']:.3f}"
        _out(f"{dim:<26}{v['n']:>5}{v['agreement']:>11.3f}{kappa:>8}  {v['status']}")
    note = "" if report["enough_items"] else " (fewer than 50)"
    _out(f"{report['labelled_items']} labelled item(s){note} -> {path}")
    return 0


def cmd_draft(a) -> int:
    from tools.agent_tests.draft import draft_spec, write_draft
    from tools.agent_tests.llm import make_llm
    _load_env()
    path = os.path.join(dataset.agent_dir(a.agent, a.root), dataset.SPEC_FILE)
    if os.path.exists(path):
        _out(f"{path} exists; a draft never overwrites a spec")
        return 1
    with open(a.brd, encoding="utf-8") as f:
        brd = f.read()
    reqs = None
    if a.requirements:
        with open(a.requirements, encoding="utf-8") as f:
            reqs = json.load(f)
    spec, dropped = draft_spec(make_llm(a.connector, a.model), a.agent, brd, reqs)
    write_draft(path, spec)
    _out(f"Draft written: {path} ({len(spec.acs)} criteria, {len(spec.kb.docs)} KB facts, "
         f"{len(spec.kb.unanswerable)} unanswerable). Review it, then run generate.")
    for why in dropped:
        _out(f"  dropped: {why}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.agent_tests", description="Phase 9 AI-agent testing")
    p.add_argument("--root", default=None, help="dataset root (default: eval_sets/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate / refresh the golden dataset")
    g.add_argument("--agent", required=True)
    g.add_argument("--seed", type=int, default=7)
    g.set_defaults(fn=cmd_generate)

    ls = sub.add_parser("list", help="list cases")
    ls.add_argument("--agent", required=True)
    ls.add_argument("--dimension", choices=DIMENSIONS)
    ls.add_argument("--unreviewed", action="store_true")
    ls.add_argument("--ac")
    ls.set_defaults(fn=cmd_list)

    rv = sub.add_parser("review", help="mark cases as human-reviewed")
    rv.add_argument("--agent", required=True)
    rv.add_argument("--ids", nargs="+")
    rv.add_argument("--dimension", choices=DIMENSIONS)
    rv.add_argument("--all", action="store_true")
    rv.add_argument("--by", required=True)
    rv.set_defaults(fn=cmd_review)

    va = sub.add_parser("validate", help="validate the dataset")
    va.add_argument("--agent", required=True)
    va.set_defaults(fn=cmd_validate)

    rn = sub.add_parser("run", help="run the dataset against a live agent")
    rn.add_argument("--agent", required=True)
    rn.add_argument("--url", required=True)
    rn.add_argument("--seed", type=int, default=7)
    rn.add_argument("--run-id")
    rn.add_argument("--k", type=int, default=None, help="runs per case (default: per dimension, 3 or 5)")
    rn.add_argument("--dimension", nargs="+", choices=DIMENSIONS)
    rn.add_argument("--canary-sys", help="the system-prompt canary you planted in the agent for this run")
    rn.add_argument("--judge", action="store_true", help="LLM judge for what the deterministic checks cannot decide")
    rn.add_argument("--workers", type=int, default=1)
    rn.add_argument("--history-dir", help="regression history directory (default .aqp_artifacts/agent_quality)")
    rn.add_argument("--no-history", action="store_true")
    rn.add_argument("--out")
    rn.set_defaults(fn=cmd_run)

    b = sub.add_parser("bench", help="buggy_bot benchmark: every weakness on / off")
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--in-process", action="store_true")
    b.add_argument("--weakness", nargs="+")
    b.add_argument("--repeat", type=int, default=None,
                   help="mock: runs per configuration (default 1); llm: baseline repeats (default 3)")
    b.add_argument("--label", default="phase9")
    b.add_argument("--no-write", action="store_true")
    b.add_argument("--llm", action="store_true", help="real-LLM bot + LLM judge (uses API credits)")
    b.add_argument("--bot-model", default="gemini-3.5-flash-lite")
    b.add_argument("--workers", type=int, default=6)
    b.add_argument("--k", type=int, default=None)
    b.set_defaults(fn=cmd_bench)

    ca = sub.add_parser("calibrate", help="judge calibration: export a labelling sheet / compute Cohen's kappa")
    ca.add_argument("action", choices=["export", "compute"])
    ca.add_argument("--agent", required=True)
    ca.add_argument("--from", dest="from_", nargs="+", default=[], help="run / benchmark result JSON(s) (export)")
    ca.add_argument("--out", default="calibration_sheet.csv")
    ca.add_argument("--target", type=int, default=None, help="items (default: >= 10 per judged dimension, >= 50)")
    ca.add_argument("--seed", type=int, default=0)
    ca.add_argument("--labels", help="the labelled CSV (compute)")
    ca.add_argument("--judge-model", help="the judge model the labels were collected for (default: agent.yaml)")
    ca.set_defaults(fn=cmd_calibrate)

    dr = sub.add_parser("draft", help="draft eval_sets/<agent>/agent.yaml from a BRD (one LLM call)")
    dr.add_argument("--agent", required=True)
    dr.add_argument("--brd", required=True)
    dr.add_argument("--requirements", help="requirements JSON (Phase 1 shape) to pin AC ids")
    dr.add_argument("--connector", default="gemini")
    dr.add_argument("--model", default="gemini-3.6-flash")
    dr.set_defaults(fn=cmd_draft)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # ✓ / ≤ must not crash a cp1252 Windows console
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
