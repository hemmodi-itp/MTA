# RepoAnalysisAgent

Reads the downloaded repository and asks Gemini for an **application profile** (`agent_profile`; the key name is
unchanged for compatibility). The profile says what the app is for, what it can and can't do, and how a user or
client reaches it once deployed. The app is **not** assumed to be an AI agent. It may be a chatbot or agent, a form
app, a document generator, a dashboard, an API, a CLI or a library.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `repo_dir` | string | yes | From RepoFetchAgent |
| `repo_tree` | array | no | The commit's full file list, so the tree and languages reflect the whole repo |
| `repo_full_name`, `repo_metadata` | string, object | no | Context for the prompt (fenced) |
| `live_url` | string | no | Given to Gemini so it can match routes to the deployment |
| `connector_mode` | string | no | LLM connector override |

## Outputs
- `agent_profile`: contains:
  - purpose, domain, capabilities, out_of_scope, tools_and_integrations, llm_providers and tech_stack;
  - `interface`: {`type`, framework, endpoints[{method, path, input_field, request_body_example, output_field}]}. `type` is one of `http_api`, `web_chat_ui`, `web_form_app`, `document_generator`, `dashboard`, `cli`, `library` or `unknown`. The first five values are the original set, so older consumers keep working;
  - entry_points, run_command and `observed_risks`;
  - `languages` and `file_count`;
  - `degraded: true` when the profile was built without the LLM.
- `code_digest`, `file_tree`, `brd_candidates`: unchanged.

`observed_risks` is passed to RepositoryReviewAgent (via the shared `agent_profile`) as hints that the review must
confirm and locate in the code. It is also shown on the run page.

## Behaviour
1. `tools/agent_eval/repo_scan.py` ranks files and packs them into a budget of about 180k characters. The ranking is: README and manifests, then entry points, then prompts, then source, then docs, then stylesheets and tests.
2. One Gemini JSON call returns the profile, using the extended interface enum (`prompt.APP_PROFILE_SCHEMA`).
3. The repository name and description, the file tree and the code digest are fenced with `fence_untrusted`. The prompt carries `UNTRUSTED_RULE`.

## Failure modes
- **Empty repository:** `failed` and blocking.
- **Gemini error or invalid JSON:** `status: partial` with `error`. The agent builds a minimal profile without the LLM:
  - the name and the first paragraph of the README;
  - frameworks taken from requirements.txt, pyproject or package.json;
  - an interface type inferred from those frameworks;
  - route patterns from the digest.

  The run continues.
