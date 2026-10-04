from tools.shared.skill_model import AgentSkill

SKILLS = {
    "test_data_generation": AgentSkill(
        name="Test Data Generator",
        description=(
            "Generates realistic, comprehensive test datasets from business scenarios. "
            "For each scenario you receive, identify every input field required by the steps, "
            "then produce one positive dataset and exactly five negative variants."
        ),
        strengths=[
            "boundary value analysis",
            "equivalence partitioning",
            "negative test pattern recognition",
            "realistic data synthesis for login, registration, search, and form flows",
            "identifying field types and format rules from natural language steps",
        ],
    )
}
