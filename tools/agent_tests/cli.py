"""
cli.py — python -m tools.agent_tests <command>   (Phase 9.2 dataset workflow + runner + benchmark)

  generate --agent A [--seed N]                     spec + catalogs → eval_sets/A/*.jsonl (keeps human review)
  list     --agent A [--dimension D] [--unreviewed] [--ac AC-01.1]
  review   --agent A (--ids ID … | --dimension D | --all) --by NAME
  validate --agent A                                exit 1 on any error
  run      --agent A --url URL [--seed N] [--run-id R] [--k 1] [--dimension D …] [--canary-sys TOKEN] [--out F]
  bench    [--seed 7] [--in-process] [--weakness BOT_BUG_01 …] [--repeat 1] [--no-write]
"""

import argparse
import datetime as _dt
import json
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


def cmd_run(a) -> int:
    from tools.agent_eval.net_guard import BlockedTarget, check_target
    from tools.agent_tests.canaries import RunTokens
    from tools.agent_tests.runner import run_suite
    from tools.agent_tests.transport import HttpTransport

    d = dataset.agent_dir(a.agent, a.root)
    spec = dataset.spec_for(d)
    if not spec.enabled:
        _out(f"{spec.agent}: agent.yaml has enabled: false — nothing to run")
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
    run_id = a.run_id or f"run-{uuid.uuid4().hex[:12]}"
    sys_canary = a.canary_sys or spec.canaries.system_prompt_value
    tokens = RunTokens.derive(a.seed, run_id, system_canary=sys_canary).as_dict()
    if spec.canaries.system_prompt_env and not sys_canary:
        _out(f"Note: start the agent with {spec.canaries.system_prompt_env}=<token> and pass --canary-sys <token> to "
             "test system-prompt leakage; without it those checks are not_applicable.")
    result = run_suite(spec, cases, HttpTransport(a.url, spec.transport), tokens, run_id, k=a.k,
                       dimensions=a.dimension, emit=_out)
    _summary(result)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        _out(f"Wrote {a.out}")
    return 0


def _summary(result) -> None:
    _out(f"{'dimension':<26}{'outcome':<13}{'cases':>6}{'pass':>6}{'fail':>6}{'judge':>7}{'error':>7}")
    for dim, v in result["dimensions"].items():
        _out(f"{dim:<26}{v['outcome']:<13}{v['cases']:>6}{v['pass']:>6}{v['fail'] + v['non_deterministic']:>6}"
             f"{v['needs_judge']:>7}{v['error']:>7}")
    if result["cut"]:
        _out(f"{len(result['cut'])} case(s) not run: " +
             ", ".join(sorted({c['reason'] for c in result['cut']})))


def cmd_bench(a) -> int:
    from tools.agent_tests.bench import markdown, run_bench, write_report
    report = run_bench(seed=a.seed, in_process=a.in_process, only=a.weakness, repeat=a.repeat, root=a.root, emit=_out)
    _out("")
    _out(markdown(report))
    if not a.no_write:
        for p in write_report(report, label=a.label):
            _out(f"Wrote {p}")
    s = report["summary"]
    ok = s["detected"] == s["total"] and not s["baseline_false_positives"] and s["deterministic"]
    return 0 if ok else 1


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

    rn = sub.add_parser("run", help="run the dataset against a live agent (deterministic checks only)")
    rn.add_argument("--agent", required=True)
    rn.add_argument("--url", required=True)
    rn.add_argument("--seed", type=int, default=7)
    rn.add_argument("--run-id")
    rn.add_argument("--k", type=int, default=1)
    rn.add_argument("--dimension", nargs="+", choices=DIMENSIONS)
    rn.add_argument("--canary-sys", help="the system-prompt canary you planted in the agent for this run")
    rn.add_argument("--out")
    rn.set_defaults(fn=cmd_run)

    b = sub.add_parser("bench", help="buggy_bot benchmark: every weakness on / off")
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--in-process", action="store_true")
    b.add_argument("--weakness", nargs="+")
    b.add_argument("--repeat", type=int, default=1)
    b.add_argument("--label", default="phase9")
    b.add_argument("--no-write", action="store_true")
    b.set_defaults(fn=cmd_bench)
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
