"""
registry_setup.py — the default agent registry.

Every agent is registered LAZILY (registry key → dotted module path + class name),
so building the registry imports nothing; an agent's module is imported only when
that key is first built. The MTA service (api/server.py) therefore never pays for,
or breaks on, the legacy Playwright/ADK agent stack.

    build_default_registry()                 every agent (scope="all", the default)
    build_default_registry(scope="mta")      only the agent-evaluation pipeline
                                             (workflows/agent_evaluation.yaml)
    build_default_registry(scope="legacy")   only the legacy CLI pipeline
                                             (main.py / workflows/full_workflow.yaml)
"""

from typing import Dict, List, Tuple

from agents.registry import AgentRegistry

# (registry_key, module_path, class_name, ctor_kwargs)
_Entry = Tuple[str, str, str, Dict]

# Legacy CLI pipeline — main.py / cli_appevolve.py → agents/orchestrator.
LEGACY_AGENTS: List[_Entry] = [
    # MODULE 1: discovery / comprehension
    ("discovery", "agents.comprehension.discovery.agent", "DiscoveryAgent", {}),
    ("comprehension", "agents.comprehension.comprehension_agent.agent", "ComprehensionAgent", {}),  # standalone use
    # MODULE 2: test creation
    ("testdata", "agents.test_creation.testdata.agent", "TestDataAgent", {}),
    ("semantic_map", "agents.test_creation.semantic_map.agent", "SemanticMapAgent", {}),
    ("artifact_generator_intents", "agents.test_creation.artifact_generator.agent", "ArtifactGeneratorAgent", {"mode": "intents"}),
    ("artifact_generator_testcases", "agents.test_creation.artifact_generator.agent", "ArtifactGeneratorAgent", {"mode": "testcases"}),
    ("dedup", "agents.test_creation.dedup.agent", "SemanticDedupAgent", {}),
    ("script_generation", "agents.test_creation.script_generation.agent", "ScriptGenerationAgent", {}),
    ("bdd", "agents.test_creation.bdd.agent", "BDDAgent", {}),
    # MODULE 3: test execution
    ("execution", "agents.test_execution.execution.agent", "ExecutionAgent", {}),
    ("ui_execution", "agents.test_execution.ui_execution.agent", "UIExecutionAgent", {}),
    ("healing", "agents.test_execution.healing.agent", "HealingAgent", {}),
    ("reporting", "agents.test_execution.reporting.agent", "ReportingAgent", {}),
    ("locator", "agents.test_execution.locator.agent", "LocatorAgent", {}),
]

# MTA agent-evaluation pipeline — api/server.py → api/pipeline.py → workflows/agent_evaluation.yaml.
MTA_AGENTS: List[_Entry] = [
    ("repo_fetch", "agents.comprehension.repo_fetch.agent", "RepoFetchAgent", {}),
    ("repo_intelligence", "agents.comprehension.repo_intelligence.agent", "RepoIntelligenceAgent", {}),
    ("repo_analysis", "agents.comprehension.repo_analysis.agent", "RepoAnalysisAgent", {}),
    ("runtime_discovery", "agents.comprehension.runtime_discovery.agent", "RuntimeDiscoveryAgent", {}),
    ("app_classification", "agents.comprehension.app_classification.agent", "AppClassificationAgent", {}),
    ("brd_builder", "agents.comprehension.brd_builder.agent", "BrdBuilderAgent", {}),
    ("agent_test_generation", "agents.test_creation.agent_test_generation.agent", "AgentTestGenerationAgent", {}),
    ("action_generation", "agents.test_creation.action_generation.agent", "ActionGenerationAgent", {}),
    ("playwright_executor", "agents.test_execution.playwright_executor.agent", "PlaywrightExecutorAgent", {}),
    ("evidence_collection", "agents.test_execution.evidence_collection.agent", "EvidenceCollectionAgent", {}),
    ("live_agent_execution", "agents.test_execution.live_agent_execution.agent", "LiveAgentExecutionAgent", {}),
    ("output_validation", "agents.evaluation.output_validation.agent", "OutputValidationAgent", {}),
    ("pass_fail", "agents.evaluation.pass_fail.agent", "PassFailAgent", {}),
    ("requirement_traceability", "agents.evaluation.requirement_traceability.agent", "RequirementTraceabilityAgent", {}),
    ("repository_review", "agents.evaluation.repository_review.agent", "RepositoryReviewAgent", {}),
    ("brd_compliance", "agents.evaluation.brd_compliance.agent", "BrdComplianceAgent", {}),
    ("compliance_scoring", "agents.evaluation.compliance_scoring.agent", "ComplianceScoringAgent", {}),
    ("final_report", "agents.evaluation.final_report.agent", "FinalReportAgent", {}),
]

_SCOPES = {
    "mta": (MTA_AGENTS,),
    "legacy": (LEGACY_AGENTS,),
    "all": (LEGACY_AGENTS, MTA_AGENTS),
}


def build_default_registry(scope: str = "all") -> AgentRegistry:
    """Return a registry with every agent in *scope* registered lazily.

    scope: "mta" | "legacy" | "all" (default). No agent module is imported here.
    """
    if scope not in _SCOPES:
        raise ValueError(f"Unknown registry scope '{scope}' — expected one of {sorted(_SCOPES)}")
    registry = AgentRegistry()
    for group in _SCOPES[scope]:
        for key, module_path, class_name, ctor_kwargs in group:
            registry.register_lazy(key, module_path, class_name, **ctor_kwargs)
    return registry
