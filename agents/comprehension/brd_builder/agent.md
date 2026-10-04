# BrdBuilderAgent

Step of the agent-evaluation pipeline that runs after RuntimeDiscoveryAgent. Decides **which BRD the run is
judged against**, then extracts requirements that are provably taken from it.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `mode` | string | yes | `brd_and_live` \| `live_only` \| `brd_only` |
| `repo_dir`, `repo_full_name` | string | yes | From RepoFetchAgent |
| `brd_path` | string | no | Repo-relative path **or** a GitHub blob/raw URL of the file |
| `brd_candidates` | array | no | Auto-detected document paths from RepoAnalysisAgent |
| `agent_profile`, `code_digest` | object, string | yes | From RepoAnalysisAgent |
| `live_url` | string | no | Used to build the BRD from the live app when there is no BRD |
| `runtime_profile` | object | no | RuntimeDiscoveryAgent output (authenticated crawl: pages, headings, forms and field labels, buttons, downloads, chat box, api_calls). Preferred live evidence. |

## Outputs
- `brd_source`: `repository` \| `generated_live` (written from the live app) \| `generated` (written from the code)
- `brd_path`: repo-relative path, or null when generated
- `brd_markdown`: full BRD text. Documents without a text layer are transcribed by Gemini.
- `requirements`: at most 40, each
  `{code: "REQ-01", title, description, priority, kind, verifiability, origin, confidence, self_generated, section, source_quote,
  criteria: [{code: "AC-01.1", statement, oracle_hint, verifiability, grounded, confidence, self_generated}], acceptance_criteria[]}`
  (at most 8 criteria per requirement).
- `ungrounded_criteria`: criterion codes whose wording could not be traced to the BRD.
- `limitations`: sentences for the final report. Every cap or uncertain choice is listed here and is never applied silently.

## Behaviour
1. **Explicit path.** `normalize_brd_path` accepts `docs/BRD.pdf`, `/docs/BRD.pdf`, `docs%20x/BRD.pdf` or
   `https://github.com/<owner>/<repo>/blob/<branch>/<path>`, and rejects links to other repos. Only that file is used.
   If it's missing or unreadable, the step **fails** and lists the documents it did find. It never switches silently.
2. **Auto-detect** (BRD modes, no path). Only the **opening** of up to 4 candidates is read (`read_brd_preview`).
   Image-only PDFs get just their first pages transcribed. Gemini then picks the document that describes *this* agent,
   rejecting TSDs, one-pagers and other products' BRDs. Only the chosen document is read in full. If the selector call fails,
   the first readable candidate is used, with a warning and a limitation saying the choice was not confirmed. If no candidate
   matches, a BRD is generated.
3. **Generate.**
   - `live_only`, or no BRD but a live URL: the evidence comes from `runtime_profile` through
     `live_discovery.evidence_from_runtime_profile`. That covers the app profile and user flows, each page's headings, forms
     with field labels, types and options, buttons, downloads and chat box, plus the API calls. Only when the profile is absent,
     or shows nothing but a login wall, does `live_discovery.collect_live_evidence` crawl the app itself. That crawl goes through
     the SSRF-guarded HTTP opener and browser. In that case the agent's answers to capability questions are recorded as
     `agent_claim` evidence: a capability supported only by a claim goes under "Assumptions", never into a requirement.
   - Otherwise it writes the BRD from the code, citing source files.
4. **Read.** `tools/agent_eval/brd_source.read_brd` extracts the text. A PDF/DOCX with under 150 chars per page is
   read visually by Gemini (`GeminiConnector.transcribe_document`, cached by document hash). Text beyond 150,000 chars
   is cut and reported as a limitation.
5. **Extract.** Gemini transcribes the requirements the BRD explicitly states, each with a verbatim `source_quote`, and
   gives each criterion its own `verifiability` (it defaults to the requirement's).
   `BrdIndex.grounded` checks every quote against the BRD text (tolerant of whitespace, punctuation and case), and
   requirements that can't be traced are **discarded**. Each criterion is then checked with `BrdIndex.support`: at least
   70% of its content words must occur in the BRD. Ungrounded criteria stay, with `grounded: false` and confidence × 0.6.
6. **Provenance.** `repository` → origin `brd`, confidence 1.0. `generated_live` → origin `inferred`, confidence ≤ 0.6.
   `generated` → origin `descriptive`, confidence 0.3. Requirements from any generated BRD have `self_generated: true`,
   because their quotes only show that MTA quoted MTA's own document. The scorer reports them as inferred conformance.

All untrusted text (documents, code, README, live evidence, code-analysis summary) is fenced in the prompts
(`FencedTemplate` + `UNTRUSTED_RULE`).

## Failure mode
`status: failed, blocking: true` for a bad or missing explicit path, an unreadable BRD, a failed generation, or
no traceable requirement. `limitations` is returned on failures too.
