"""
registry.py — name → agent-constructor lookup shared by the MTA service
(api/pipeline.py) and the legacy CLI orchestrator (agents/orchestrator).

Two ways to register an agent:

  register(name, agent_cls)                       eager: the class (or any callable
                                                  returning an agent) is already imported
  register_lazy(name, module_path, class_name,    lazy: only the dotted path is stored;
                **ctor_kwargs)                    the module is imported on first
                                                  get()/build() for that name

Lazy registration keeps one agent's import cost (or import error) from leaking into
every other agent: building "repo_fetch" never imports the Playwright/ADK-heavy
legacy agents, and a broken legacy import only fails the step that needs it.
"""

import importlib
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass(frozen=True)
class LazyAgentSpec:
    module_path: str
    class_name: str
    ctor_kwargs: Dict[str, Any] = field(default_factory=dict)

    def load(self) -> Callable:
        module = importlib.import_module(self.module_path)
        cls = getattr(module, self.class_name)
        return partial(cls, **self.ctor_kwargs) if self.ctor_kwargs else cls


class AgentRegistry:
    def __init__(self):
        self._registry: Dict[str, Callable] = {}
        self._lazy: Dict[str, LazyAgentSpec] = {}

    def register(self, name: str, agent_cls: Callable) -> None:
        """Register an already-imported agent class (or factory)."""
        self._lazy.pop(name, None)
        self._registry[name] = agent_cls

    def register_lazy(self, name: str, module_path: str, class_name: str, **ctor_kwargs) -> None:
        """Register an agent by dotted module path + class name; nothing is
        imported until get()/build() is called for *name*. Extra keyword
        arguments are bound into the constructor (like functools.partial)."""
        self._registry.pop(name, None)
        self._lazy[name] = LazyAgentSpec(module_path, class_name, dict(ctor_kwargs))

    def get(self, name: str) -> Callable:
        if name in self._registry:
            return self._registry[name]
        spec = self._lazy.get(name)
        if spec is None:
            raise KeyError(f"Agent '{name}' is not registered")
        agent_cls = spec.load()          # ImportError/AttributeError propagate to the caller
        self._registry[name] = agent_cls  # cache — import once
        del self._lazy[name]
        return agent_cls

    def build(self, name: str, *args, **kwargs):
        agent_cls = self.get(name)
        return agent_cls(*args, **kwargs)

    def spec(self, name: str) -> Optional[LazyAgentSpec]:
        """The lazy spec for *name*, or None if it is eager or already loaded."""
        return self._lazy.get(name)

    def keys(self) -> List[str]:
        return sorted(set(self._registry) | set(self._lazy))

    def __contains__(self, name: object) -> bool:
        return name in self._registry or name in self._lazy

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(set(self._registry) | set(self._lazy))
