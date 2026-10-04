from abc import ABC, abstractmethod
from typing import Any, Dict, List


class DBConnector(ABC):
    """Abstract base for database connectors (future: Postgres, DynamoDB, etc.)."""

    @abstractmethod
    def query(self, sql: str, params: List[Any] = None) -> List[Dict]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, sql: str, params: List[Any] = None) -> None:
        raise NotImplementedError
