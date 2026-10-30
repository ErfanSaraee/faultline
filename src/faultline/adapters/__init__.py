"""Agent adapter contracts, registry, and built-in implementations."""

from faultline.adapters.base import AgentAdapter, ToolHandler, default_mock_tool_handler
from faultline.adapters.mock_agent import DeterministicMockAgent
from faultline.adapters.registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "AgentAdapter",
    "DeterministicMockAgent",
    "ToolHandler",
    "default_mock_tool_handler",
]
