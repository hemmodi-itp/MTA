"""
brd_source.py — read the BRD reliably and keep everything derived from it traceable.

  normalize_brd_path()  "…/blob/main/docs/BRD.pdf", "/docs/BRD.pdf", "docs%20x/BRD.pdf" → "docs/BRD.pdf"
  read_brd()            text extraction; falls back to Gemini's multimodal PDF/DOCX read when
                        the file has no usable text layer (scanned / outlined-font PDFs)
  read_brd_preview()    only the opening of a candidate document (for picking which document is the BRD)
  BrdIndex.grounded()   does a quote really occur in the BRD? (whitespace/punctuation/case-insensitive,
                        tolerant of PDF line-break hyphenation and small transcription differences)
  BrdIndex.support()    token-overlap grounding for restated acceptance criteria (0-1)
"""

import re
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from tools.comprehension.parse_document import parse_document

# Below this many characters per page, a PDF's text layer is treated as unusable.
MIN_CHARS_PER_PAGE = 150
MIN_BRD_CHARS = 200
MAX_BRD_CHARS = 150_000
# share of a criterion's content words that must occur in the BRD for it to count as grounded
CRITERION_SUPPORT = 0.7

_TRANSCRIBE_INSTRUCTION = (
    "Transcribe this document to Markdown faithfully and completely. Keep every heading, "
    "requirement ID, table (as a Markdown table) and bullet exactly as written. "
    "Do not summarise, reorder, add, interpret or invent anything. Output only the transcription."
)
PREVIEW_CHARS = 3_500
_PREVIEW_INSTRUCTION = (
    "Transcribe ONLY the opening of this document to Markdown — its title, any product / system name, the "
    "table of contents and the first section — stopping after about {chars} characters. Do not summarise or "
    "invent anything. Output only the transcription."
)
_MIME = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def normalize_brd_path(raw: Optional[str], repo_full_name: Optional[str] = None) -> Optional[str]:
    """Turn whatever the user pasted into a repo-relative POSIX path (None if empty)."""
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    m = re.match(
        r"^https?://(?:www\.)?(?:github\.com|raw\.githubusercontent\.com)/([^/]+)/([^/]+)/(?:(?:blob|raw|tree)/)?([^?#]+)",
        value,
    )
    if m:
        owner, repo, rest = m.groups()
        if repo_full_name and f"{owner}/{repo}".lower() != repo_full_name.lower():
            raise ValueError(f"The BRD link points at {owner}/{repo}, not the submitted repository {repo_full_name}.")
        # rest = "<branch>/<path…>" — drop the branch segment
        value = rest.split("/", 1)[1] if "/" in rest else ""
    value = urllib.parse.unquote(value).replace("\\", "/").strip().lstrip("/")
    if ".." in value.split("/"):
        raise ValueError("The BRD path must stay inside the repository.")
    return value or None


def _pdf_pages(path: Path) -> int:
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(path)) as pdf:
            return max(1, len(pdf.pages))
    except Exception:
        return 1


def _extract_text(path: Path, emit) -> str:
    try:
        return parse_document(str(path)).content.strip()
    except Exception as exc:
        emit(f"Text extraction failed for {path.name}: {exc}", "warning")
        return ""


def _needs_vision(path: Path, text: str) -> bool:
    ext = path.suffix.lower()
    return ext in _MIME and (
        len(text) < MIN_BRD_CHARS or (ext == ".pdf" and len(text) / _pdf_pages(path) < MIN_CHARS_PER_PAGE)
    )


def _cap(text: str, name: str, emit, limitations: Optional[List[str]]) -> str:
    if len(text) <= MAX_BRD_CHARS:
        return text
    msg = (f"The BRD {name} has {len(text):,} characters; only the first {MAX_BRD_CHARS:,} were used — "
           "requirements stated after that point were not evaluated.")
    emit(msg, "warning")
    if limitations is not None:
        limitations.append(msg)
    return text[:MAX_BRD_CHARS]


def read_brd(path: Path, llm, emit: Callable[[str, str], None] = lambda *a: None,
             limitations: Optional[List[str]] = None) -> Tuple[str, str]:
    """Return (text, method). method is 'text' or 'gemini_transcription'. Raises ValueError if unreadable.

    A document longer than MAX_BRD_CHARS is cut, with a warning, and (when `limitations` is given) a
    sentence describing the cut is appended to it for the run report.
    """
    ext = path.suffix.lower()
    text = _extract_text(path, emit)

    if _needs_vision(path, text):
        transcribe = getattr(llm, "transcribe_document", None)
        if transcribe is None:
            raise ValueError(f"{path.name} has no readable text layer and the LLM connector can't read documents visually.")
        emit(f"{path.name} has no usable text layer ({len(text)} chars) — reading it visually with Gemini.", "info")
        text = (transcribe(path.read_bytes(), _MIME[ext], _TRANSCRIBE_INSTRUCTION) or "").strip()
        text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text)
        if len(text) < MIN_BRD_CHARS:
            raise ValueError(f"{path.name} could not be read, even visually.")
        return _cap(text, path.name, emit, limitations), "gemini_transcription"

    if len(text) < MIN_BRD_CHARS:
        raise ValueError(f"{path.name} contains only {len(text)} characters — too little to be a BRD.")
    return _cap(text, path.name, emit, limitations), "text"


def read_brd_preview(path: Path, llm, emit: Callable[[str, str], None] = lambda *a: None,
                     chars: int = PREVIEW_CHARS) -> Tuple[str, bool]:
    """Opening text of a candidate document, for deciding WHICH document is the BRD.

    Returns (preview, complete). complete=True means the preview came from the full text layer, so the
    full document needs no second read. Image-only documents are transcribed only up to their opening pages
    (a short output instead of the whole document); the chosen one is then transcribed fully by read_brd.
    Raises ValueError if nothing can be read.
    """
    ext = path.suffix.lower()
    text = _extract_text(path, emit)
    if not _needs_vision(path, text):
        if len(text) < MIN_BRD_CHARS:
            raise ValueError(f"{path.name} contains only {len(text)} characters — too little to be a BRD.")
        return text[:chars], len(text) <= MAX_BRD_CHARS
    transcribe = getattr(llm, "transcribe_document", None)
    if transcribe is None:
        raise ValueError(f"{path.name} has no readable text layer and the LLM connector can't read documents visually.")
    emit(f"{path.name} has no usable text layer — reading its opening pages visually to identify it.", "info")
    text = (transcribe(path.read_bytes(), _MIME[ext], _PREVIEW_INSTRUCTION.format(chars=chars)) or "").strip()
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text)
    if len(text) < 40:
        raise ValueError(f"{path.name} could not be read, even visually.")
    return text[:chars], False


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
        q = _norm(quote or "")
        if len(q) < 12:
            return False
        if q in self.text:
            return True
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
