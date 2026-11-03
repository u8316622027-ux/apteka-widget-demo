"""Shared MCP tool descriptor type."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    output_template: str
    ui: dict[str, Any]
    title: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    tool_invocation: dict[str, str] = field(default_factory=dict)
    visibility: str = "public"
    listed: bool = True
