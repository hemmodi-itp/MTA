"""semantic_map_prompt.py — LLM prompt template for SemanticMapAgent."""

from string import Template

SEMANTIC_MAP_PROMPT = Template("""
You are a QA architect. Given a list of business scenarios and a list of UI DOM elements,
identify which DOM elements are relevant to each scenario.

For each scenario, return 3-7 elements that a test script would actually interact with.
Include only elements directly used in the scenario steps (inputs, buttons, links, headings).
Omit cookie banners, nav menus, and unrelated UI chrome unless a scenario step explicitly touches them.

== Business Scenarios ==
$scenarios_json

== Available DOM Elements ==
$elements_json

Return ONLY a valid JSON object. No markdown, no explanation.

Format:
{
  "BS-001": {
    "scenario_title": "Scenario title here",
    "relevant_elements": [
      {
        "locator_id": "LOC-0002",
        "playwright_expr": "page.getByPlaceholder('Search Products ...')",
        "relevance": "primary search input — used in step 1"
      }
    ]
  }
}

Rules:
- Use the exact locator_id and playwright_expr values from the provided element list.
- relevance must be a plain-English phrase explaining why this element is used.
- 3 elements minimum, 7 maximum per scenario.
- Omit scenarios that have zero relevant elements (they will get test.skip stubs).
- Return ONLY the JSON object.
""")
