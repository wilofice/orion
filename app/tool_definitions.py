from typing import List
from tool_wrappers import TOOL_REGISTRY
from gemini_interface import ToolDefinition

TOOL_DEFINITIONS: List[ToolDefinition] = [
    {
        "name": name,
        "description": wrapper.description,
        "parameters": wrapper.parameters_schema,
    }
    for name, wrapper in TOOL_REGISTRY.items()
]
