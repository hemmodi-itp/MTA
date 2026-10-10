"""
tools.safety — Phase 0 safety rails (shared core; usable by the legacy pipeline
and the Agent-Evaluation DAG alike).

  policy.py            project.yaml `environment:` + `safety:` -> SafetyPolicy
  hosts.py             allowed_hosts parsing / matching
  action_classifier.py deterministic destructive-action classifier
  payloads.py          active security-probe payload detector
  plan_filter.py       applies the policy to an action-library test plan
"""
