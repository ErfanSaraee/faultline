"""Pydantic v2 schemas for Project and AgentConfig API contracts."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")

AdapterType = Literal["mock", "langgraph", "http_proxy"]


class ProjectCreate(BaseModel):
    """Payload required to create a new Project workspace."""

    slug: str = Field(
        min_length=3,
        max_length=64,
        description="URL-safe unique identifier (kebab-case, e.g. 'research-agent')",
    )
    name: str = Field(
        min_length=1,
        max_length=128,
        description="Human-readable project name",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional description of the project purpose",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, value: str) -> str:
        if not SLUG_PATTERN.match(value):
            raise ValueError(
                "Slug must contain only lowercase alphanumeric characters and single hyphens."
            )
        return value


class ProjectResponse(BaseModel):
    """Serialized Project representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class AgentConfigCreate(BaseModel):
    """Payload required to register a versioned AgentConfig under a Project."""

    name: str = Field(
        min_length=1,
        max_length=128,
        description="Logical name of the agent (e.g. 'rag-assistant')",
    )
    version: int = Field(
        default=1,
        ge=1,
        le=10000,
        description="Explicit positive integer configuration version",
    )
    adapter_type: AdapterType = Field(
        description="Integration adapter type ('mock', 'langgraph', or 'http_proxy')"
    )
    model_name: str = Field(
        min_length=1,
        max_length=128,
        description="Model identifier used by the agent (e.g. 'gpt-4o-mini', 'mock-v1')",
    )
    system_prompt: str | None = Field(
        default=None,
        max_length=10000,
        description="Optional system instructions or persona summary",
    )
    config_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive adapter parameters (e.g. timeouts, max_steps, temperature)",
    )
    secret_refs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of logical credential keys to environment variable names "
            "(e.g. {'api_key': 'OPENAI_API_KEY'}). Raw secrets are strictly rejected."
        ),
    )

    @field_validator("secret_refs")
    @classmethod
    def validate_secret_references(cls, value: dict[str, str]) -> dict[str, str]:
        for logical_key, env_var_name in value.items():
            if not logical_key.strip():
                raise ValueError(
                    "Secret reference logical key cannot be empty.")
            if not ENV_VAR_NAME_PATTERN.match(env_var_name):
                raise ValueError(
                    f"Invalid secret reference '{env_var_name}' for key '{logical_key}'. "
                    "Must be an uppercase environment variable name (e.g. 'OPENAI_API_KEY'), "
                    "never a raw credential or secret value."
                )
        return value


class AgentConfigResponse(BaseModel):
    """Serialized AgentConfig representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    version: int
    adapter_type: str
    model_name: str
    system_prompt: str | None
    config_payload: dict[str, Any]
    secret_refs: dict[str, str]
    created_at: datetime
    updated_at: datetime
