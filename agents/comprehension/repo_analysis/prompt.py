"""prompt.py — LLM prompt template and output schema for RepoAnalysisAgent.

The evaluated application is not assumed to be an AI agent: it may be a chatbot or agent, a form app, a document
generator, a dashboard, an API, a CLI or a library. Repository content (name, description, file tree, code) is
fenced as untrusted data by the agent before substitution.
"""

import copy
from string import Template

from tools.agent_eval.schemas import AGENT_PROFILE

# Backward compatible: the original five values stay valid (live_client treats web_chat_ui as UI-first).
INTERFACE_TYPES = ["http_api", "web_chat_ui", "web_form_app", "document_generator", "dashboard", "cli", "library",
                   "unknown"]

# The shared schema with the extended interface vocabulary (a local copy; tools/agent_eval/schemas.py is unchanged).
APP_PROFILE_SCHEMA = copy.deepcopy(AGENT_PROFILE)
APP_PROFILE_SCHEMA["properties"]["interface"]["properties"]["type"] = {"type": "string", "enum": INTERFACE_TYPES}

REPO_ANALYSIS_PROMPT = Template("""$skill_header
You are a senior application reviewer. Below is the source of a GitHub repository. It may be an AI agent or
chatbot, but it may equally be a web form application, a document generator, a dashboard, a REST/GraphQL API,
a CLI tool, a library, or a mix. Work out what the application is FOR, who uses it, and exactly how a user or
client interacts with it once deployed. Do not assume it uses an LLM; say so only if the code does.

$untrusted_rule

Detected languages: $languages
Live URL supplied by the user: $live_url

## Repository name and GitHub description
$repo_info

## File tree
$file_tree

## Key file contents
$code_digest

## Output
Return ONE JSON object, exactly this shape (use null / [] when the code doesn't tell you — never invent):
{
  "agent_name": "short name of the application",
  "purpose": "2-4 sentences: what problem the application solves and for whom",
  "domain": "e.g. customer support, travel booking, HR forms, finance reporting",
  "target_users": ["..."],
  "capabilities": ["concrete things the application can do, one per item"],
  "out_of_scope": ["things the code explicitly refuses or doesn't handle"],
  "tools_and_integrations": ["external APIs, tools, databases, vector stores, file formats it uses"],
  "llm_providers": ["e.g. OpenAI gpt-4o, Gemini, Anthropic — empty if it uses no LLM"],
  "tech_stack": ["frameworks and key libraries"],
  "system_prompt_summary": "what the app's own LLM system prompt tells it to do, or null if there is none",
  "interface": {
    "type": "http_api | web_chat_ui | web_form_app | document_generator | dashboard | cli | library | unknown",
    "framework": "fastapi | flask | django | express | nestjs | nextjs | react | vue | spring | rails | streamlit | gradio | chainlit | other | unknown",
    "endpoints": [
      {
        "method": "POST",
        "path": "/api/...",
        "description": "what it does",
        "input_field": "dotted path of the main user-supplied field, e.g. message or input.question (if any)",
        "request_body_example_json": "{\\"message\\": \\"hello\\"}  (the example request body, serialised as a JSON string)",
        "output_field": "dotted path of the main result in the JSON response (if any)"
      }
    ],
    "auth_required": false,
    "notes": "anything a tester must know (login, session ids, streaming, required headers, file downloads)"
  },
  "entry_points": ["files that start the app"],
  "run_command": "how the app is started, e.g. uvicorn app:app",
  "observed_risks": ["security / reliability issues visible in the code, with the file, e.g. hard-coded keys in config.py"]
}

Rules for interface.type:
- web_chat_ui: the user talks to it through a chat box (Streamlit/Gradio/Chainlit chat, a web chat page).
- web_form_app: the user fills in forms that create or update records.
- document_generator: the main output is a generated file or document (DOCX, PDF, report) to download.
- dashboard: the main output is charts, tables or metrics to look at.
- http_api: no UI of its own; clients call its HTTP endpoints.
- cli / library: run from a terminal / imported by other code.
List the HTTP routes a user's main actions go through in interface.endpoints, the main one first.
observed_risks are hints for a later code review that verifies them; name the file for each.
Base everything on the code shown. No markdown, no commentary — JSON only.
""")
