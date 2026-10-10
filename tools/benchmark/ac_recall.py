"""
ac_recall.py — Phase 1 acceptance check: how many hand-labelled acceptance criteria does extraction find?

    python -m tools.benchmark.ac_recall --app buggy_shop                 # BRD as written (declared ids)
    python -m tools.benchmark.ac_recall --app buggy_shop --strip-ids     # ids removed: the LLM must find them
    python -m tools.benchmark.ac_recall --app buggy_shop --no-llm        # deterministic path only

Each module's BRD is the same per-module split the benchmark feeds MTA (materialize.split_brd). Extraction runs
in a temporary registry, so no project is touched. A ground-truth AC counts as extracted when an extracted
criterion (a criterion or an atomic child) matches it by TEXT — its quote is grounded in the ground-truth
statement, or it restates ≥ 70% of the statement's content words — never by id. Writes
benchmarks/results/<date>_<app>_ac_recall[_stripped].json and prints the summary; exit code 1 when recall is
below --min-recall (default 0.9).
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date
from typing import Any, Dict, List, Optional

from tools.benchmark.apps import APPS, REPO_ROOT, load_ac_truth
from tools.benchmark.materialize import split_brd

TEXT_SUPPORT = 0.7
_ID_TOKEN = re.compile(r"\(?`?\b(?:REQ-\d+|AC-\d+(?:\.\d+)+|AC-xx\.y|REQ-xx)\b`?\)?:?\s?")


def strip_ids(text: str) -> str:
    """Remove every REQ/AC id token so extraction can't rely on declared ids."""
    return _ID_TOKEN.sub("", text)


def match_score(gt_statement: str, extracted: Dict[str, Any]) -> float:
    """1.0 when the extracted criterion's quote (or statement) is grounded in the ground-truth statement, else
    the share of its content words found there. A small tie-breaker prefers the closer restatement."""
    from tools.requirements.brd_index import BrdIndex

    gt = BrdIndex(gt_statement)
    stmt = extracted.get("statement") or ""
    quoted = gt.grounded(extracted.get("source_quote")) and not extracted.get("parent_id")
    base = 1.0 if quoted or gt.grounded(stmt) else gt.support(stmt)
    return base + 0.01 * BrdIndex(stmt).support(gt_statement)


def matches(gt_statement: str, extracted: Dict[str, Any]) -> bool:
    return match_score(gt_statement, extracted) >= TEXT_SUPPORT


def _best(gt_statement: str, pool: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    scored = [(match_score(gt_statement, c), i) for i, c in enumerate(pool)]
    scored = [x for x in scored if x[0] >= TEXT_SUPPORT]
    return pool[max(scored)[1]] if scored else None


def score_recall(truth: List[dict], extracted: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Pure scorer. extracted = {module_id: [criterion dicts]}. Matching stays within the module first, then
    falls back project-wide (a shared BRD section may place a criterion under another module)."""
    every = [c for cs in extracted.values() for c in cs]
    rows, used = [], set()
    for gt in truth:
        pool = extracted.get(gt.get("module"), []) or []
        hit = _best(gt["statement"], pool) or _best(gt["statement"], every)
        if hit is not None:
            used.add(id(hit))
        row = {"id": gt["id"], "module": gt.get("module"), "extracted": hit is not None,
               "matched_id": hit.get("id") if hit else None}
        if hit is not None:
            row.update({
                "testability": [gt.get("testability"), hit.get("testability")],
                "priority": [gt.get("priority"), hit.get("priority")],
                "risk_tags": [sorted(gt.get("risk_tags") or []), sorted(hit.get("risk_tags") or [])],
                "atomic": [gt.get("atomic", True), not hit.get("children") and hit.get("atomic", True)],
            })
        rows.append(row)
    found = [r for r in rows if r["extracted"]]

    def agree(key: str) -> Optional[float]:
        return round(sum(1 for r in found if r[key][0] == r[key][1]) / len(found), 3) if found else None

    def jaccard() -> Optional[float]:
        if not found:
            return None
        vals = []
        for r in found:
            a, b = set(r["risk_tags"][0]), set(r["risk_tags"][1])
            vals.append(1.0 if not a and not b else len(a & b) / len(a | b))
        return round(sum(vals) / len(vals), 3)

    # A matched criterion's family (its parent, its atomic children, its siblings) is not "unmatched": an LLM
    # split of a hand-labelled criterion is the same requirement at a finer grain.
    matched_ids = {r["matched_id"] for r in found}
    family = set(matched_ids)
    for c in every:
        if c.get("id") in matched_ids and c.get("parent_id"):
            family.add(c["parent_id"])
    unmatched = [c for c in every if id(c) not in used and c.get("id") not in family
                 and c.get("parent_id") not in family]

    return {
        "total": len(truth),
        "extracted": len(found),
        "recall": round(len(found) / len(truth), 4) if truth else None,
        "missed": [r["id"] for r in rows if not r["extracted"]],
        "agreement": {"testability": agree("testability"), "priority": agree("priority"),
                      "atomic": agree("atomic"), "risk_tags_jaccard": jaccard()},
        "criteria_extracted": len(every),
        "unmatched_extractions": len(unmatched),
        "unmatched_statements": [c.get("statement", "")[:160] for c in unmatched],
        "rows": rows,
    }


def extract_all(app_name: str, strip: bool, llm) -> Dict[str, Any]:
    from tools.requirements.extract import extract_requirements
    from tools.requirements.ids import IdAllocator
    from tools.state.artifact_registry import ArtifactRegistry

    app = APPS[app_name]
    with open(app.brd_path, encoding="utf-8") as fh:
        brd = fh.read()
    per_module = split_brd(brd, app.module_reqs)
    extracted: Dict[str, List[Dict[str, Any]]] = {}
    statuses: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        allocator = IdAllocator(ArtifactRegistry(tmp))
        reserved: Dict[str, str] = {}      # as in the pipeline: ids/text other modules already hold
        for module_id, text in per_module.items():
            res = extract_requirements(strip_ids(text) if strip else text, llm, allocator=allocator,
                                       module_id=module_id, module_label=module_id, reserved=reserved)
            extracted[module_id] = [ac.model_dump() for r in res.requirements for ac in r.acceptance_criteria]
            for r in res.requirements:
                reserved[r.id] = r.title
                reserved.update({ac.id: ac.statement for ac in r.acceptance_criteria})
            statuses[module_id] = {"status": res.status, "rejected": len(res.rejected),
                                   "warnings": len(res.warnings), "limitations": res.limitations}
    return {"extracted": extracted, "modules": statuses}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", default="buggy_shop", choices=sorted(APPS))
    ap.add_argument("--strip-ids", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--min-recall", type=float, default=0.9)
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "benchmarks", "results"))
    args = ap.parse_args(argv)

    from tools.requirements.build import _llm
    truth = load_ac_truth(APPS[args.app])
    if not truth:
        print(f"error: {APPS[args.app].acs_yaml} not found")
        return 2
    run = extract_all(args.app, args.strip_ids, _llm(args.no_llm))
    result = score_recall(truth, run["extracted"])
    result.update({"app": args.app, "date": date.today().isoformat(), "strip_ids": args.strip_ids,
                   "llm": not args.no_llm, "modules": run["modules"],
                   "extracted_criteria": {m: [{k: c.get(k) for k in ("id", "parent_id", "statement", "testability",
                                                             "priority", "risk_tags", "source_quote")}
                                     for c in cs] for m, cs in run["extracted"].items()}})
    os.makedirs(args.out, exist_ok=True)
    suffix = "_stripped" if args.strip_ids else ""
    suffix += "_nollm" if args.no_llm else ""
    path = os.path.join(args.out, f"{result['date']}_{args.app}_ac_recall{suffix}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(f"AC extraction recall ({args.app}, strip_ids={args.strip_ids}, llm={not args.no_llm}): "
          f"{result['extracted']}/{result['total']} = {result['recall']:.1%}")
    print(f"  missed: {', '.join(result['missed']) or 'none'}")
    print(f"  agreement with hand labels: {result['agreement']}")
    print(f"  extracted criteria not matching any hand-labelled AC: {result['unmatched_extractions']}")
    print(f"  written: {os.path.relpath(path, REPO_ROOT)}")
    return 0 if (result["recall"] or 0) >= args.min_recall else 1


if __name__ == "__main__":
    sys.exit(main())
