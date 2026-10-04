from typing import List, Optional
from pydantic import BaseModel


class DomIntent(BaseModel):
    intent_id: str
    intent_name: str
    action: str
    locator_id: Optional[str] = None
    selector: Optional[str] = None
    display_text: Optional[str] = None


class DiscoveryResult(BaseModel):
    mode: str                          # "both" | "brd_only" | "url_only"
    project: str
    scenarios_count: int = 0
    dom_intents_count: int = 0
    business_scenarios_path: Optional[str] = None
    dom_intents_path: Optional[str] = None
    dom_elements_path: Optional[str] = None
    synthetic_brd_path: Optional[str] = None
