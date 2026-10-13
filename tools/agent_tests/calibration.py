"""
calibration.py — is the LLM judge trustworthy, per dimension? (Phase 9.3, design §14 S4)

    python -m tools.agent_tests calibrate export  --agent A --from run.json --out sheet.csv   # ≥ 50 items to label
    python -m tools.agent_tests calibrate compute --agent A --labels sheet.csv                # κ per dimension

1. export: every judged run (pass / fail / unsure) of one or more run results goes into a CSV, stratified across
   dimensions, with an empty `human_label` column (pass | fail | skip). A human fills it in — MTA cannot.
2. compute: Cohen's κ between judge and human per dimension, on items both labelled pass/fail. A dimension is
   VERIFIED when n ≥ min_items_per_dimension and κ ≥ min_kappa (0.6); the result is written to
   eval_sets/<agent>/calibration.json and the Judge reads it: unverified dimensions get "unverified_judge".
"""

import csv
import json
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tools.agent_tests.config import CALIBRATION
from tools.agent_tests.judge import conversation_text

CALIBRATION_FILE = "calibration.json"
COLUMNS = ["item_id", "case_id", "dimension", "run", "judge_verdict", "judge_score", "judge_reasoning", "rubric",
           "conversation", "human_label", "human_notes"]
LABELS = ("pass", "fail")


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> Optional[float]:
    """Cohen's κ for two raters over the same items: (p_o − p_e) / (1 − p_e).

    None when there are no items. When both raters give one and the same label to every item, p_e = 1 and κ is
    undefined; it is reported as 1.0 (perfect agreement) by convention."""
    if len(a) != len(b):
        raise ValueError("raters must label the same items")
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in set(ca) | set(cb))
    if pe >= 1.0:
        return 1.0 if po == 1.0 else None
    return (po - pe) / (1 - pe)


def judged_items(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every run a judge looked at, flattened for labelling."""
    items = []
    for res in results:
        for rec in res.get("cases") or []:
            for i, run in enumerate(rec.get("runs") or []):
                j = run.get("judge")
                if not j:
                    continue
                items.append({"item_id": f"{res.get('run_id')}:{rec['id']}:{i}", "case_id": rec["id"],
                              "dimension": rec["dimension"], "run": i, "judge_verdict": j.get("verdict"),
                              "judge_score": j.get("score"), "judge_reasoning": (j.get("reasoning") or "")[:600],
                              "rubric": rec.get("rubric") or "", "conversation": conversation_text(run)[:3000],
                              "human_label": "", "human_notes": ""})
    return items


def stratified(items: List[Dict[str, Any]], target: int, seed: int = 0) -> List[Dict[str, Any]]:
    """Round-robin across dimensions so every judged dimension gets labels; deterministic for a seed."""
    rng = random.Random(f"calibration:{seed}")
    by_dim: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        by_dim[it["dimension"]].append(it)
    for lst in by_dim.values():
        rng.shuffle(lst)
    out: List[Dict[str, Any]] = []
    while len(out) < target and any(by_dim.values()):
        for dim in sorted(by_dim):
            if by_dim[dim] and len(out) < target:
                out.append(by_dim[dim].pop())
    return out


def export_sheet(results: Iterable[Dict[str, Any]], path: str, target: Optional[int] = None,
                 seed: int = 0) -> Tuple[int, int]:
    """Write the labelling CSV. Returns (items written, items available).

    Default target: enough for every judged dimension to reach min_items_per_dimension labels (and at least
    min_items overall) — fewer per dimension could never verify it, however well the judge agrees."""
    items = judged_items(results)
    if target is None:
        dims = len({i["dimension"] for i in items})
        target = max(CALIBRATION["min_items"], dims * CALIBRATION["min_items_per_dimension"])
    chosen = stratified(items, max(target, 0) or len(items), seed)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for it in chosen:
            w.writerow(it)
    return len(chosen), len(items)


def read_labels(path: str) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def compute(rows: List[Dict[str, str]], min_items_per_dimension: int = CALIBRATION["min_items_per_dimension"],
            min_kappa: float = CALIBRATION["min_kappa"]) -> Dict[str, Any]:
    """κ per dimension from a labelled sheet. Rows whose human_label or judge_verdict is not pass/fail are skipped."""
    by_dim: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    skipped = 0
    for r in rows:
        human = (r.get("human_label") or "").strip().lower()
        judge = (r.get("judge_verdict") or "").strip().lower()
        if human in LABELS and judge in LABELS:
            by_dim[r.get("dimension") or "?"].append((judge, human))
        else:
            skipped += 1
    dims: Dict[str, Any] = {}
    for dim, pairs in sorted(by_dim.items()):
        judge_l, human_l = [p[0] for p in pairs], [p[1] for p in pairs]
        kappa = cohens_kappa(judge_l, human_l)
        n = len(pairs)
        agree = sum(1 for j, h in pairs if j == h) / n
        status = ("insufficient_labels" if n < min_items_per_dimension else
                  "verified" if kappa is not None and kappa >= min_kappa else "unverified")
        dims[dim] = {"n": n, "agreement": round(agree, 4), "kappa": None if kappa is None else round(kappa, 4),
                     "status": status}
    labelled = sum(d["n"] for d in dims.values())
    return {"min_kappa": min_kappa, "min_items_per_dimension": min_items_per_dimension, "labelled_items": labelled,
            "skipped_rows": skipped, "enough_items": labelled >= CALIBRATION["min_items"], "dimensions": dims}


@dataclass
class Calibration:
    dimensions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    judge_model: Optional[str] = None

    @classmethod
    def load(cls, directory: str) -> "Calibration":
        path = os.path.join(directory, CALIBRATION_FILE)
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("dimensions") or {}, data.get("judge_model"))

    def is_verified(self, dimension: str) -> bool:
        return (self.dimensions.get(dimension) or {}).get("status") == "verified"

    def verified_dimensions(self) -> List[str]:
        return sorted(d for d, v in self.dimensions.items() if v.get("status") == "verified")

    def applies_to(self, judge_model: Optional[str]) -> bool:
        """A calibration is only valid for the judge model it was measured on."""
        return self.judge_model is None or judge_model is None or self.judge_model == judge_model


def save(directory: str, report: Dict[str, Any], judge_model: Optional[str]) -> str:
    path = os.path.join(directory, CALIBRATION_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({**report, "judge_model": judge_model}, f, indent=2, sort_keys=True)
        f.write("\n")
    return path
