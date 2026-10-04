"""
ComprehensionAgent — orchestrates the five-step comprehension pipeline.

    parse_all_documents
        → extract_requirements   (LLM, per document)
        → generate_business_scenarios  (LLM, combined)
        → validate_business_scenarios
        → export_scenarios
            → application_assets/projects/<project>/comprehension/
                business_scenarios.json
                business_scenarios.md
"""

import os
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.comprehension.comprehension_agent.tools import (
    export_scenarios,
    extract_requirements,
    generate_business_scenarios,
    load_existing_titles_by_module,
    parse_all_documents,
    validate_business_scenarios,
)
from connectors.connector_registry import ConnectorRegistry
from tools.comprehension.models import Actor, BusinessRule, Requirement, Workflow
from tools.shared import get_logger
from tools.state.artifact_registry import ArtifactRegistry

from tools.constants import PROJECTS_BASE as _ASSETS_BASE


class ComprehensionAgent(BaseAgent):
    """
    Reads requirement artifacts and produces structured Business Scenarios.

    Request keys:
        project_name (str, optional) — used as the output sub-directory name.
                                       Falls back to request["message"] then "project".
        input_dir    (str, optional) — override the default input directory.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.comprehension")

    # ------------------------------------------------------------------

    def execute(self, request: dict, state: dict) -> Dict:
        project_name = (
            request.get("project_name")
            or request.get("message", "project")
        )
        input_dir = request.get("brd_dir") or request.get("input_dir") or os.path.join(_ASSETS_BASE, _safe_name(project_name), "inputs")
        output_dir = os.path.join(_ASSETS_BASE, _safe_name(project_name), "test_comprehension")
        modules = request.get("modules")  # list of {id, name, brd_file} dicts, or None

        self.logger.info(f"[ComprehensionAgent] Starting — project='{project_name}'")
        self.logger.info(f"[ComprehensionAgent] Input: {input_dir}")
        self.logger.info(f"[ComprehensionAgent] Output dir: {output_dir}")
        if modules:
            self.logger.info(f"[ComprehensionAgent] Modular mode — {len(modules)} module(s): {[m['id'] for m in modules]}")

        llm = self._registry.get_llm()
        project_dir = os.path.join(_ASSETS_BASE, _safe_name(project_name))
        artifact_registry = ArtifactRegistry(project_dir)

        if modules:
            return self._execute_modular(request, project_name, input_dir, output_dir, modules, llm, artifact_registry)
        return self._execute_flat(request, project_name, input_dir, output_dir, llm, artifact_registry)

    def _execute_modular(self, request: dict, project_name: str, input_dir: str, output_dir: str, modules: list, llm, artifact_registry: ArtifactRegistry) -> Dict:
        """Per-module comprehension: each module's BRD processed separately; scenarios tagged with module_id."""
        all_valid_scenarios = []
        total_docs = 0
        total_reqs = 0
        total_rules = 0
        total_actors = 0
        total_workflows = 0
        all_warnings = []
        skipped_modules: List[Dict[str, str]] = []
        module_ids = [m["id"] for m in modules]
        existing_titles_by_module = load_existing_titles_by_module(output_dir)

        for mod in modules:
            mod_id = mod["id"]
            mod_name = mod.get("name", mod_id)
            brd_file = mod.get("brd_file")

            if brd_file:
                brd_path = os.path.join(input_dir, brd_file)
                if not os.path.exists(brd_path):
                    self.logger.warning(f"[ComprehensionAgent] Module {mod_id}: BRD file not found at '{brd_path}' — skipping")
                    skipped_modules.append({"module_id": mod_id, "reason": f"BRD file not found at '{brd_path}'"})
                    continue
                self.logger.info(f"[ComprehensionAgent] Module {mod_id} ({mod_name}): parsing '{brd_file}'")
                from tools.comprehension.parse_document import parse_document
                documents = [parse_document(brd_path)]
            else:
                # No brd_file specified — parse entire input_dir for this module (non-modular fallback)
                documents = parse_all_documents(input_dir)

            if not documents:
                self.logger.warning(f"[ComprehensionAgent] Module {mod_id}: no documents parsed — skipping")
                skipped_modules.append({"module_id": mod_id, "reason": "no documents parsed"})
                continue

            total_docs += len(documents)

            # Extract
            mod_requirements: List[Requirement] = []
            mod_rules: List[BusinessRule] = []
            mod_actors: List[Actor] = []
            mod_workflows: List[Workflow] = []

            for doc in documents:
                try:
                    extracted = extract_requirements(doc, llm)
                except ValueError as exc:
                    self.logger.error(f"Module {mod_id}: extraction failed for '{doc.file_name}': {exc}")
                    continue
                mod_requirements.extend(extracted["requirements"])
                mod_rules.extend(extracted["business_rules"])
                mod_actors.extend(extracted["actors"])
                mod_workflows.extend(extracted["workflows"])

            self.logger.info(
                f"[ComprehensionAgent] Module {mod_id}: extracted {len(mod_requirements)} reqs, "
                f"{len(mod_rules)} rules, {len(mod_actors)} actors, {len(mod_workflows)} workflows"
            )
            total_reqs += len(mod_requirements)
            total_rules += len(mod_rules)
            total_actors += len(mod_actors)
            total_workflows += len(mod_workflows)

            # Generate — stamped with module_id and module_name.
            # existing_titles_by_module tells the LLM what's already covered
            # for this module so a re-run on an edited BRD doesn't re-propose
            # scenarios that already exist under different wording.
            existing_for_module = existing_titles_by_module.get(mod_id, [])
            try:
                scenarios = generate_business_scenarios(
                    project_name=project_name,
                    requirements=mod_requirements,
                    business_rules=mod_rules,
                    actors=mod_actors,
                    workflows=mod_workflows,
                    llm_provider=llm,
                    module_id=mod_id,
                    module_name=mod_name,
                    registry=artifact_registry,
                    existing_scenarios=existing_for_module,
                )
                artifact_registry.save()
            except ValueError as exc:
                self.logger.error(f"Module {mod_id}: scenario generation failed: {exc}")
                skipped_modules.append({"module_id": mod_id, "reason": f"scenario generation failed: {exc}"})
                continue

            self.logger.info(f"[ComprehensionAgent] Module {mod_id}: generated {len(scenarios)} scenario(s)")

            # Validate
            valid, warnings = validate_business_scenarios(scenarios)
            for w in warnings:
                self.logger.warning(f"Module {mod_id} validation: {w}")
            all_warnings.extend(warnings)
            all_valid_scenarios.extend(valid)

            # Persist this module's scenarios immediately (merge-upsert, so
            # other modules' already-written scenarios are preserved) — if a
            # caller-side timeout abandons this run partway through the loop,
            # every module that finished before the deadline is already on
            # disk instead of being lost with the rest of the in-memory work.
            if valid:
                export_scenarios(valid, output_dir, project_name, module_ids=[mod_id])
                self.logger.info(
                    f"[ComprehensionAgent] Module {mod_id}: checkpointed {len(valid)} "
                    "scenario(s) to disk"
                )

        if not all_valid_scenarios:
            return {
                "module": "comprehension",
                "status": "failed",
                "project": project_name,
                "error": "No scenarios generated across any module",
                "skipped_modules": skipped_modules,
            }

        # Final export — a no-op beyond what the per-module checkpoints above
        # already wrote, but keeps the returned `paths` and log line intact.
        paths = export_scenarios(all_valid_scenarios, output_dir, project_name, module_ids=module_ids)
        for p in (paths or {}).values():
            self.logger.info(f"[ComprehensionAgent] Written: {p}")
        self.logger.info(f"[ComprehensionAgent] Done — {len(all_valid_scenarios)} scenarios exported across {len(modules)} module(s)")

        status = "partial" if skipped_modules else "success"
        result = {
            "module": "comprehension",
            "status": status,
            "project": project_name,
            "modular": True,
            "modules_processed": len(modules) - len(skipped_modules),
            "documents_parsed": total_docs,
            "requirements_extracted": total_reqs,
            "rules_extracted": total_rules,
            "actors_identified": total_actors,
            "workflows_identified": total_workflows,
            "scenarios_generated": len(all_valid_scenarios),
            "scenarios_valid": len(all_valid_scenarios),
            "validation_warnings": all_warnings,
            "output": paths,
        }
        if skipped_modules:
            result["skipped_modules"] = skipped_modules
            result["error"] = (
                f"{len(skipped_modules)}/{len(modules)} module(s) skipped: "
                + "; ".join(f"{s['module_id']} ({s['reason']})" for s in skipped_modules)
            )
        return result

    def _execute_flat(self, request: dict, project_name: str, input_dir: str, output_dir: str, llm, artifact_registry: ArtifactRegistry) -> Dict:
        """Original flat (non-modular) comprehension pipeline — unchanged behaviour."""
        # Step 1 — Parse
        self.logger.info(f"Parsing BRD from '{input_dir}'")
        documents = parse_all_documents(input_dir)

        if not documents:
            self.logger.warning(f"[ComprehensionAgent] No supported documents found in '{input_dir}'")
            self.logger.warning("[ComprehensionAgent] Supported formats: .txt .md .json .pdf .docx")
            return {
                "module": "comprehension",
                "status": "no_input",
                "project": project_name,
                "message": (
                    f"No supported documents found at '{input_dir}'. "
                    "Provide a directory containing BRD files, or a direct file path. "
                    "Supported formats: .txt .md .json .pdf .docx"
                ),
            }

        self.logger.info(f"[ComprehensionAgent] Loaded {len(documents)} input file(s):")
        for doc in documents:
            self.logger.info(f"[ComprehensionAgent]   ✓ {doc.file_name} ({doc.source_type})")

        # Step 2 — Extract
        all_requirements: List[Requirement] = []
        all_rules: List[BusinessRule] = []
        all_actors: List[Actor] = []
        all_workflows: List[Workflow] = []

        for doc in documents:
            self.logger.info(f"Extracting from '{doc.file_name}' ({doc.source_type})")
            try:
                extracted = extract_requirements(doc, llm)
            except ValueError as exc:
                self.logger.error(f"Extraction failed for '{doc.file_name}': {exc}")
                continue
            all_requirements.extend(extracted["requirements"])
            all_rules.extend(extracted["business_rules"])
            all_actors.extend(extracted["actors"])
            all_workflows.extend(extracted["workflows"])

        self.logger.info(
            f"Extracted {len(all_requirements)} requirements, "
            f"{len(all_rules)} rules, "
            f"{len(all_actors)} actors, "
            f"{len(all_workflows)} workflows"
        )

        # Step 3 — Generate
        self.logger.info("Generating business scenarios")
        try:
            scenarios = generate_business_scenarios(
                project_name=project_name,
                requirements=all_requirements,
                business_rules=all_rules,
                actors=all_actors,
                workflows=all_workflows,
                llm_provider=llm,
                registry=artifact_registry,
            )
            artifact_registry.save()
        except ValueError as exc:
            self.logger.error(f"Scenario generation failed: {exc}")
            return {
                "module": "comprehension",
                "status": "failed",
                "project": project_name,
                "error": str(exc),
            }

        self.logger.info(f"Generated {len(scenarios)} scenario(s)")

        # Step 4 — Validate
        valid_scenarios, warnings = validate_business_scenarios(scenarios)
        for w in warnings:
            self.logger.warning(f"Validation: {w}")

        # Step 5 — Export
        paths = export_scenarios(valid_scenarios, output_dir, project_name)
        for p in (paths or {}).values():
            self.logger.info(f"[ComprehensionAgent] Written: {p}")
        self.logger.info(f"[ComprehensionAgent] Done — {len(valid_scenarios)} scenarios exported")

        return {
            "module": "comprehension",
            "status": "success",
            "project": project_name,
            "documents_parsed": len(documents),
            "requirements_extracted": len(all_requirements),
            "rules_extracted": len(all_rules),
            "actors_identified": len(all_actors),
            "workflows_identified": len(all_workflows),
            "scenarios_generated": len(scenarios),
            "scenarios_valid": len(valid_scenarios),
            "validation_warnings": warnings,
            "output": paths,
        }


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"


class ComprehensionAgentStub(BaseAgent):
    """python_stub fallback tier for the `comprehension` step
    (workflows/agent_registry.yaml → fallback_class, disabled by default).

    Last resort when ComprehensionAgent and the NS reroute both fail: no LLM, no
    HTTP, no files written. It returns an explicitly flagged empty result
    (stub=True, scenarios_count=0) so the run completes and the gap is visible in
    the report, instead of the orchestrator inventing scenarios.
    """

    MODULE_NAME = "comprehension"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.comprehension")

    def execute(self, request: dict, state: dict) -> Dict:
        project_name = request.get("project_name") or request.get("message", "project")
        self.logger.warning(
            f"[ComprehensionAgentStub] python_stub tier used for project '{project_name}' — "
            "no business scenarios were generated; re-run comprehension once the LLM/NS is reachable"
        )
        return {
            "status": "success",
            "stub": True,
            "project": project_name,
            "business_scenarios_path": None,
            "scenarios_count": 0,
            "reason": "comprehension python_stub fallback — no scenarios generated",
        }
