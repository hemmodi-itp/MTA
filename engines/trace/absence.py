"""
absence.py — the absence protocol: may a criterion be judged `not_implemented`?

Absence is the strongest negative claim the evaluation makes, so it needs (a) a real negative search — the verifier
says concretely what it looked for and retrieval had enough candidates to look at — and (b) an index that covers
where the code would live. `absence_check` returns (ok, reason); when not ok, decide.py turns a `not_implemented`
into `insufficient_evidence` and shows the reason.

Coverage comes from two places:
  * repo_coverage (RepoFetchAgent): the tree listing was truncated, or files could not be fetched;
  * repo_model["coverage"] (indexer): source files listed but not fetched (budget) or fetched but not indexed
    (too large, generated, file cap, unsupported language), with sample paths.
A gap blocks absence when it is relevant to the claim (a missing file's path shares a word with the search terms),
or when it is large (more than MAX_MISSING_SHARE of the repository's source files), or when the listing itself is
truncated (unknown files can hold anything).
"""

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from engines.trace.retrieve import tokenize

MIN_HITS_FOR_ABSENCE = 5
MAX_MISSING_SHARE = 0.10
_GENERIC = {"code", "function", "file", "implementation", "logic", "handler", "feature", "support", "check",
            "value", "data", "the", "any", "none", "nothing"}


def concrete_looked_for(looked_for: Iterable[str]) -> List[str]:
    """The items of a verifier's `looked_for` that name something searchable (not just 'the code')."""
    out = []
    for item in looked_for or []:
        toks = [t for t in tokenize(str(item)) if t not in _GENERIC and len(t) >= 3]
        if toks:
            out.append(str(item))
    return out


def _path_tokens(path: str) -> set:
    return set(tokenize(re.sub(r"[/._\-]", " ", path)))


def absence_check(n_hits: int, looked_for: Sequence[str], terms: Sequence[str],
                  index_coverage: Optional[Dict] = None, repo_coverage: Optional[Dict] = None) -> Tuple[bool, Optional[str]]:
    if not concrete_looked_for(looked_for):
        return False, "the code review did not list anything concrete it searched for"
    if n_hits < MIN_HITS_FOR_ABSENCE:
        return False, f"retrieval found only {n_hits} candidate code chunk(s), too few to rule the behaviour out"
    rc, ic = repo_coverage or {}, index_coverage or {}
    if rc.get("truncated"):
        return False, f"the repository listing was truncated ({rc.get('truncation_reason') or 'GitHub limit'})"
    missing = list(ic.get("unfetched_source") or []) + list(ic.get("unindexed_source") or [])
    n_missing = int(ic.get("unfetched_source_count") or 0) + int(ic.get("unindexed_source_count") or 0)
    if not n_missing:
        return True, None
    want = set(tokenize(" ".join(list(terms) + list(looked_for))))
    relevant = [p for p in missing if want & _path_tokens(p)]
    if relevant:
        return False, (f"{n_missing} source file(s) are not in the index, including {len(relevant)} whose names match "
                       f"the search (e.g. {', '.join(relevant[:3])})")
    indexed = int(ic.get("files_indexed") or 0)
    if indexed and n_missing / (indexed + n_missing) > MAX_MISSING_SHARE:
        return False, f"{n_missing} of {indexed + n_missing} source files are not in the index"
    if n_missing > len(missing):  # only a sample of the paths is known; the rest could match
        return False, f"{n_missing} source files are not in the index and not all of them could be checked"
    return True, None
