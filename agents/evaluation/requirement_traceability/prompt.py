"""prompt.py — LLM prompt templates (and the verifier's output schema) for RequirementTraceabilityAgent.

Everything that comes from the evaluated repository or its BRD — requirement text, criteria, the repository
vocabulary, wiring paths and code — is passed in through tools.agent_eval.untrusted.fence_untrusted, which also
neutralises any fence tags inside it.
"""

import copy
from string import Template

from tools.agent_eval.schemas import QUERY_TERMS, VERIFIER
from tools.agent_eval.untrusted import UNTRUSTED_RULE

PREAMBLE = f"""You are one stage of an evaluation pipeline. Your output is machine-checked.
- {UNTRUSTED_RULE}
- Never state a fact you cannot point to in the provided code. Cite exact file paths and the line
  numbers printed at the start of each code line; citations are validated and false ones void your answer.
- If the code shown is not enough to decide, say so with status insufficient_evidence."""

# Shared schema plus a self-reported confidence (not required, so older connectors / caches stay valid).
# The agent only uses it to decide whether a second verifier sample is worth its cost.
VERIFIER_SCHEMA = copy.deepcopy(VERIFIER)
VERIFIER_SCHEMA["properties"]["confidence"] = {"type": "string", "enum": ["high", "medium", "low"]}
QUERY_TERMS_SCHEMA = QUERY_TERMS

QUERY_EXPANSION_PROMPT = Template("""$preamble

For each acceptance criterion below, list what the code implementing it is likely to contain:
identifiers, function or class names, library names, route paths, UI labels, config keys, file-name
words. The repository's routes, pages and agents are given so you can use its real vocabulary.
Rank by specificity; at most 15 terms per criterion. Do not guess file paths.

## Repository vocabulary
$vocabulary

## Requirements and their acceptance criteria
$requirements

Return {"criteria": [{"code": "AC-..", "terms": ["..."]}]} with one entry per criterion code listed.
""")

VERIFIER_PROMPT = Template("""$preamble

Decide whether the code shown implements ONE acceptance criterion of a requirement.

## Requirement ($req_code, $req_kind, verifiability: $verifiability)
$req_text

## Acceptance criterion $crit_code
$criterion

## How the retrieved code is wired (routes and their callers)
$paths

## Retrieved code (each line starts with its line number)
$code

## Decide
status:
- implemented: a code path performs exactly the stated behaviour. Cite the lines that do it.
- partial: it does some of it, or relies only on an LLM prompt instruction where the criterion needs
  enforcement, or handles the happy path but not the stated condition.
- not_implemented: ONLY if the code shown covers the places this behaviour would have to live and
  none of it does it. List in looked_for the concrete identifiers, routes, labels or files you searched for.
- insufficient_evidence: ONLY when none of the code shown relates to the criterion. A clear
  implementation, or a call path whose names and parameters show the behaviour (a route taking
  `excluded_sections` and passing it on, a function named for the behaviour doing it), is enough to
  decide - you do not need to see every function it calls. When a key piece is missing, prefer
  partial and list it in need_more.
A stated number (latency, count, size, percentage) cannot be proven by reading code: at most partial.
Each citation: file (exactly as in the header), start_line, end_line, symbol (function/class name, if
any), claim (one sentence: what those lines do for the criterion, naming the identifiers involved).
need_more: if you answer insufficient_evidence or partial because the deciding code is referenced but not
shown (an imported component, a called service method, a config file), list those exact names (symbols,
components or file names, at most 6). Otherwise an empty list.
confidence: high only when the cited lines leave no reasonable doubt; low when you are mostly guessing.
""")
