"""
brd_index.py — quote and criterion grounding against a source document (pure Python, no I/O, no LLM).

Moved here from tools/agent_eval/brd_source.py (Phase 1.4) so the legacy pipeline and the Agent-Evaluation
DAG share one verifier; brd_source re-exports BrdIndex unchanged.

  BrdIndex.grounded()            does a quote really occur in the document? (whitespace/punctuation/case-insensitive,
                                 tolerant of PDF line-break hyphenation and small transcription differences)
  BrdIndex.quote_match()         "exact" | "fuzzy" | "none" — which test grounded() passed
  BrdIndex.support()             token-overlap grounding for restated acceptance criteria (0-1)
  BrdIndex.criterion_grounded()  support() >= CRITERION_SUPPORT
"""

import re
from difflib import SequenceMatcher
from typing import Optional

# share of a criterion's content words that must occur in the BRD for it to count as grounded
CRITERION_SUPPORT = 0.7
MIN_QUOTE_CHARS = 12


# ── grounding ────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.lower().replace("-\n", "")
    s = re.sub(r"[`*_#>|]", " ", s)  # markdown noise from transcriptions
    s = re.sub(r"[^\w%$.,:/+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .,:")


class BrdIndex:
    """Normalised BRD text for fast repeated quote checks."""

    def __init__(self, brd_text: str) -> None:
        self.text = _norm(brd_text)
        self.words = self.text.split()
        self._stems: Optional[set] = None

    def grounded(self, quote: Optional[str], min_ratio: float = 0.85) -> bool:
        return self.quote_match(quote, min_ratio) != "none"

    def quote_match(self, quote: Optional[str], min_ratio: float = 0.85) -> str:
        """"exact" (normalised substring), "fuzzy" (a near-identical word window) or "none"."""
        q = _norm(quote or "")
        if len(q) < MIN_QUOTE_CHARS:
            return "none"
        if q in self.text:
            return "exact"
        return "fuzzy" if self._fuzzy(q, min_ratio) else "none"

    def _fuzzy(self, q: str, min_ratio: float) -> bool:
        # Tolerate small transcription / paraphrase-of-punctuation differences: slide a
        # window of the quote's length over the BRD and look for a near match.
        qwords = q.split()
        n = len(qwords)
        if n < 3 or n > 120:
            return False
        # Anchor on the quote's rarest-looking (longest) word, then compare equal-length
        # word windows that could contain the quote around each occurrence of it.
        anchor_pos, anchor = max(enumerate(qwords), key=lambda iw: len(iw[1]))
        for i, w in enumerate(self.words):
            if w != anchor:
                continue
            for shift in (-2, -1, 0, 1, 2):
                start = i - anchor_pos + shift
                if start < 0:
                    continue
                window = " ".join(self.words[start:start + n])
                if SequenceMatcher(None, q, window, autojunk=False).ratio() >= min_ratio:
                    return True
        return False

    def support(self, statement: Optional[str]) -> float:
        """Share (0-1) of a statement's content words that occur in the BRD (fuzzy token-overlap grounding).

        Acceptance criteria are often restated rather than quoted ("split X and Y into two"), so they can't be
        held to the verbatim test of grounded(); a restated criterion still uses the document's own words.
        Simple plural / -ed / -ing variants count as the same word.
        """
        if self.grounded(statement):
            return 1.0
        words = [w for w in _norm(statement or "").split() if len(w) > 2 and w not in _STOP]
        if not words:
            return 0.0
        if self._stems is None:
            self._stems = {_stem(w) for w in self.words}
        return sum(1 for w in words if _stem(w) in self._stems) / len(words)

    def criterion_grounded(self, statement: Optional[str], threshold: float = CRITERION_SUPPORT) -> bool:
        return self.support(statement) >= threshold


_STOP = set("the and for with that this from are was were has have had not but any all can will shall must should "
            "may its their them they then than when what which who whom into onto upon each per via also only such "
            "able user users system app application".split())


def _stem(word: str) -> str:
    w = word.strip(".,:/+")
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return w
