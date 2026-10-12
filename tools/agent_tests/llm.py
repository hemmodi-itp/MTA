"""
llm.py — build an LLM connector for a SPECIFIC model (judge / agent under test).

The connector registry resolves Gemini's model through AQP_GEMINI_MODEL first, which would let one environment
variable silently give the judge and the agent under test the same model. Here the model is passed to the
constructor, which wins over every other source (design §14 S1).
"""

from typing import Optional


def make_llm(connector: str = "gemini", model: Optional[str] = None, use_cache: bool = True):
    if connector == "gemini":
        from connectors.llm.gemini import GeminiConnector
        return GeminiConnector(model=model, use_cache=use_cache)
    from connectors.connector_registry import ConnectorRegistry
    return ConnectorRegistry({"connectors": {"llm": connector}}).get_llm()


def model_of(llm) -> Optional[str]:
    return getattr(llm, "model", None) or getattr(llm, "model_id", None)
