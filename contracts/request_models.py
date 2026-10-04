from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class RequestModel:
    workflow: str
    message: str
    metadata: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, payload: dict) -> "RequestModel":
        return cls(
            workflow=payload.get("workflow", ""),
            message=payload.get("message", ""),
            metadata=payload.get("metadata", {}),
        )
