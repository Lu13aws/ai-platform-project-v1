"""
Agent abstraction — placeholder for Phase 2+.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    output: str
    metadata: dict = field(default_factory=dict)


class Agent(ABC):
    """Base class for all platform agents."""

    @abstractmethod
    async def run(self, input: str, **kwargs: object) -> AgentResult:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
