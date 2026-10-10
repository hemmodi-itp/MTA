"""
contracts.artifacts — Phase 0.7 artifact contracts (schema_version 2).

Pydantic models + JSON Schemas (schemas/*.v2.schema.json) for every pipeline
artifact, v1 -> v2 migrating loaders, and atomic v2 writers. See
docs/phases/phase-0-design.md §7.
"""

from contracts.artifacts.io import (
    ArtifactContractError,
    ValidationReport,
    load_payload,
    load_records,
    save_artifact,
    stamp,
    upgrade,
    validate_document,
    validate_file,
    wrap,
)
from contracts.artifacts.migrations import ArtifactVersionError, detect_version, to_v1, to_v2
from contracts.artifacts.models import SCHEMA_VERSION
from contracts.artifacts.paths import artifact_path, iter_project_artifacts
from contracts.artifacts.registry import ARTIFACTS, VERSIONED, spec_for

__all__ = [
    "ARTIFACTS", "VERSIONED", "SCHEMA_VERSION",
    "ArtifactContractError", "ArtifactVersionError", "ValidationReport",
    "artifact_path", "detect_version", "iter_project_artifacts", "load_payload", "load_records",
    "save_artifact", "spec_for", "stamp", "to_v1", "to_v2", "upgrade",
    "validate_document", "validate_file", "wrap",
]
