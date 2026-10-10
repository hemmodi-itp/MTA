"""
export_schemas.py — write the JSON Schemas of every artifact contract.

    python -m contracts.artifacts.export_schemas            # (re)write schemas/
    python -m contracts.artifacts.export_schemas --check    # exit 1 if schemas/ is stale

Output: schemas/<artifact>.v2.schema.json for versioned artifacts and
schemas/<artifact>.schema.json for plain (un-enveloped) ones.
"""

import argparse
import json
import os
import sys
from typing import Dict

from contracts.artifacts.models import SCHEMA_VERSION
from contracts.artifacts.registry import ARTIFACTS

DEFAULT_DIR = "schemas"


def schema_filename(name: str) -> str:
    spec = ARTIFACTS[name]
    return f"{name}.v{SCHEMA_VERSION}.schema.json" if spec.kind != "plain" else f"{name}.schema.json"


def build_schemas() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for name, spec in sorted(ARTIFACTS.items()):
        schema = spec.model.model_json_schema()
        if name == "locator_map":
            schema = {"type": "object", "additionalProperties": schema,
                      "title": "LocatorMap", "$defs": schema.pop("$defs", {})}
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"mta://schemas/{schema_filename(name)}"
        schema["x-mta-artifact"] = name
        schema["x-mta-kind"] = spec.kind
        out[schema_filename(name)] = schema
    return out


def _render(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_DIR)
    ap.add_argument("--check", action="store_true", help="fail if the files on disk are not up to date")
    args = ap.parse_args(argv)

    stale = []
    os.makedirs(args.out, exist_ok=True) if not args.check else None
    for fname, schema in build_schemas().items():
        path = os.path.join(args.out, fname)
        text = _render(schema)
        if args.check:
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if current != text:
                stale.append(path)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"wrote {path}")
    if args.check and stale:
        print("stale schema files (run python -m contracts.artifacts.export_schemas):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
