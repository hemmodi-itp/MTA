"""
parse_document — converts a file on disk into a structured Document.

Supported natively (no extra deps):
    .txt  .md  .json  .java  .py  .js  .ts

Optional (install separately):
    .pdf   → pip install pdfplumber
    .docx  → pip install python-docx
"""

import json
import os
from pathlib import Path
from typing import List

from tools.comprehension.models import Document

_SOURCE_CODE_EXT: dict = {
    ".java": "java",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
}

_ALL_SUPPORTED: set = {
    ".txt", ".md", ".json", ".pdf", ".docx",
    *_SOURCE_CODE_EXT.keys(),
}


def _detect_source_type(file_name: str, content: str) -> str:
    """Heuristic: infer the document's semantic type from its name."""
    n = file_name.lower()
    if any(k in n for k in ("brd", "business_requirement", "business-req")):
        return "brd"
    if any(k in n for k in ("prd", "product_requirement", "product-req")):
        return "prd"
    if any(k in n for k in ("functional", "func_spec", "functional-spec")):
        return "functional_spec"
    if any(k in n for k in ("user_stor", "story", "stories", "us-")):
        return "user_story"
    if any(k in n for k in ("acceptance", "criteria", "ac_", "ac-")):
        return "acceptance_criteria"
    if "jira" in n:
        return "jira_export"
    if "confluence" in n:
        return "confluence_export"
    # JSON heuristic: Jira bulk-export has an "issues" key
    if content.lstrip().startswith("{") and '"issues"' in content[:200]:
        return "jira_export"
    return "requirement"


def parse_document(file_path: str) -> Document:
    """Parse a single file into a Document model."""
    path = Path(file_path)
    ext = path.suffix.lower()
    file_name = path.name

    if ext not in _ALL_SUPPORTED:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {sorted(_ALL_SUPPORTED)}"
        )

    # --- Source code ---
    if ext in _SOURCE_CODE_EXT:
        content = path.read_text(encoding="utf-8", errors="replace")
        return Document(
            file_name=file_name,
            file_type=_SOURCE_CODE_EXT[ext],
            source_type="source_code",
            content=content,
            metadata={"language": _SOURCE_CODE_EXT[ext]},
        )

    # --- Plain text / Markdown ---
    if ext in (".txt", ".md"):
        content = path.read_text(encoding="utf-8", errors="replace")
        return Document(
            file_name=file_name,
            file_type="txt" if ext == ".txt" else "markdown",
            source_type=_detect_source_type(file_name, content),
            content=content,
        )

    # --- JSON (Jira export / Confluence export / generic) ---
    if ext == ".json":
        with open(file_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        content = json.dumps(raw, indent=2)
        return Document(
            file_name=file_name,
            file_type="json",
            source_type=_detect_source_type(file_name, content),
            content=content,
            metadata={"parsed_json": raw},
        )

    # --- PDF (optional dependency) ---
    if ext == ".pdf":
        try:
            import pdfplumber  # type: ignore
        except ImportError:
            raise ImportError(
                "pdfplumber is required for PDF files.  "
                "Install with: pip install pdfplumber"
            )
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(f"[Page {i}]\n{text}")
        content = "\n\n".join(parts)
        return Document(
            file_name=file_name,
            file_type="pdf",
            source_type=_detect_source_type(file_name, content),
            content=content,
        )

    # --- DOCX (optional dependency) ---
    if ext == ".docx":
        try:
            import docx  # type: ignore
        except ImportError:
            raise ImportError(
                "python-docx is required for DOCX files.  "
                "Install with: pip install python-docx"
            )
        doc = docx.Document(file_path)
        content = "\n".join(
            para.text for para in doc.paragraphs if para.text.strip()
        )
        return Document(
            file_name=file_name,
            file_type="docx",
            source_type=_detect_source_type(file_name, content),
            content=content,
        )

    raise ValueError(f"Unhandled file type '{ext}'")  # should never reach here


def parse_all_documents(input_path: str) -> List[Document]:
    """
    Parse documents from a directory or a single file path.

    - Directory: scans all supported files (non-recursive, sorted).
    - File path: parses that one file if its extension is supported.
    """
    p = Path(input_path)

    if p.is_file():
        if p.suffix.lower() in _ALL_SUPPORTED:
            return [parse_document(str(p))]
        return []

    if p.is_dir():
        documents = []
        for entry in sorted(os.listdir(input_path)):
            full_path = os.path.join(input_path, entry)
            if os.path.isfile(full_path) and Path(full_path).suffix.lower() in _ALL_SUPPORTED:
                documents.append(parse_document(full_path))
        return documents

    return []
