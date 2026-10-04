"""
run_golden.py — measure verdict accuracy of an evaluation run against a labelled golden repo.

    python evals/run_golden.py --golden evals/golden/brd_agent.json --run-id <Run id>
    python evals/run_golden.py --golden evals/golden/brd_agent.json            # latest run of that repo

Each golden requirement is matched to the run's extracted requirement with the most keyword hits
(title + description + section). Reports: coverage (golden requirements found), exact agreement,
acceptable agreement, and a per-requirement table. Reads Postgres via DATABASE_URL (repo .env or
frontend/.env), exactly like the evaluation service.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", dotenv_values(ROOT / "frontend" / ".env").get("DATABASE_URL", ""))

from connectors.db.postgres import PostgresConnector  # noqa: E402

# Requirement roll-up verdicts (engines/trace/decide.roll_up) → the golden vocabulary.
_NORMALISE = {"verified": "verified", "implemented": "implemented", "partial": "partial", "failed": "not_implemented",
              "not_implemented": "not_implemented", "insufficient_evidence": "insufficient_evidence",
              "not_technically_verifiable": "not_technically_verifiable"}


def _match(golden: dict, reqs: list) -> dict:
    def hits(r):
        text = f"{r['title']} {r['description']} {r.get('section') or ''}".lower()
        return sum(1 for k in golden["keywords"] if k.lower() in text)
    best = max(reqs, key=hits, default=None)
    return best if best and hits(best) >= 2 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--run-id")
    args = ap.parse_args()
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    db = PostgresConnector()
    run_id = args.run_id or (db.query(
        'SELECT r."id" FROM "Run" r JOIN "Project" p ON p."id" = r."projectId" '
        'WHERE p."githubUrl" ILIKE %s AND r."status" = \'completed\'::"RunStatus" AND r."scoringVersion" IS NOT NULL '
        'ORDER BY r."finishedAt" DESC LIMIT 1', [f"%{golden['repo']}%"]) or [{}])[0].get("id")
    if not run_id:
        print("No completed evidence-model run found for", golden["repo"])
        return 1
    reqs = db.query('SELECT "code","title","description","section","verdict","score" FROM "Requirement" WHERE "runId"=%s', [run_id])
    run = db.query('SELECT "complianceScore","verificationDepth","scoringVersion" FROM "Run" WHERE "id"=%s', [run_id])[0]

    rows, exact, ok, found = [], 0, 0, 0
    for g in golden["requirements"]:
        r = _match(g, reqs)
        got = _NORMALISE.get((r or {}).get("verdict") or "", (r or {}).get("verdict")) if r else None
        found += bool(r)
        exact += got == g["expected"]
        ok += got in g["acceptable"]
        rows.append((g["id"], r["code"] if r else "-", g["expected"], got or "(not extracted)", "yes" if got in g["acceptable"] else "NO"))

    n = len(golden["requirements"])
    print(f"Run {run_id} · compliance {run['complianceScore']} · depth {run['verificationDepth']} · {run['scoringVersion']}")
    print(f"{'golden':9} {'run':7} {'expected':22} {'got':24} acceptable")
    for row in rows:
        print(f"{row[0]:9} {row[1]:7} {row[2]:22} {row[3]:24} {row[4]}")
    print(f"\ncoverage {found}/{n} · exact {exact}/{n} ({exact / n:.0%}) · acceptable {ok}/{n} ({ok / n:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
