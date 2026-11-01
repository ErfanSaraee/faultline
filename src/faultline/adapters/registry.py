"""Registry mapping adapter_type identifiers to concrete AgentAdapter instances."""

from faultline.adapters.base import AgentAdapter
from faultline.adapters.langgraph_agent import LangGraphResearchAdapter
from faultline.adapters.mock_agent import DeterministicMockAgent
from faultline.core.errors import UnsupportedAdapterError


class AdapterRegistry:
    """Central registry for looking up and instantiating AgentAdapter implementations."""

    def __init__(self) -> None:
        self._adapters: dict[str, AgentAdapter] = {}
        self.register(DeterministicMockAgent())
        self.register(LangGraphResearchAdapter())

    def register(self, adapter: AgentAdapter) -> None:
        """Register an AgentAdapter instance under its adapter_type key."""
        self._adapters[adapter.adapter_type] = adapter

    def get(self, adapter_type: str) -> AgentAdapter:
        """Retrieve a registered AgentAdapter or raise UnsupportedAdapterError."""
        adapter = self._adapters.get(adapter_type)
        if adapter is None:
            raise UnsupportedAdapterError(adapter_type)
        return adapter

    def list_supported_types(self) -> list[str]:
        """Return sorted list of registered adapter_type identifiers."""
        return sorted(self._adapters.keys())
