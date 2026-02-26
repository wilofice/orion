# app/tools/base.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import Field
import pytz
from dateutil.parser import parse as dateutil_parse

from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus


class ToolWrapper(ABC):
    """
    Abstract Base Class for all tool wrappers.
    Defines the interface for the Tool Executor to interact with specific tool logic.
    """
    tool_name: str
    description: str = Field(..., description="Description of the tool.")
    parameters_schema: Dict[str, Any] = Field(
        ...,
        description="Schema defining the parameters for the tool."
    )

    @abstractmethod
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        """
        Executes the tool's logic with the provided arguments and context.

        Args:
            args: Dictionary of arguments parsed from the Gemini function call.
                  Types will likely be simple (str, int, float, bool).
            context: The ExecutionContext containing user preferences, calendar client, etc.

        Returns:
            An ExecutorToolResult indicating the outcome (success, error, clarification).
        """
        pass

    def _create_success_result(self, result_data: Dict[str, Any]) -> ExecutorToolResult:
        """Helper to create a success result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.SUCCESS, result=result_data)

    def _create_error_result(self, error_details: str, result_data: Optional[Dict[str, Any]] = None) -> ExecutorToolResult:
        """Helper to create an error result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.ERROR, error_details=error_details, result=result_data)

    def _create_clarification_result(self, prompt: str, result_data: Optional[Dict[str, Any]] = None) -> ExecutorToolResult:
        """Helper to create a clarification result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.CLARIFICATION_NEEDED, clarification_prompt=prompt, result=result_data)


# Argument Parsing Utilities

def parse_datetime_flexible(dt_str: str, user_tz: pytz.BaseTzInfo) -> Optional[datetime]:
    """
    Parses a date/time string using dateutil.parser and makes it timezone-aware.
    Handles relative terms like "tomorrow", "next Tuesday 3pm".

    Args:
        dt_str: The date/time string from Gemini.
        user_tz: The user's timezone.

    Returns:
        A timezone-aware datetime object or None if parsing fails.
    """
    if not dt_str:
        return None
    try:
        dt_naive = dateutil_parse(dt_str, fuzzy=False)
        if dt_naive.tzinfo is None:
            dt_aware = user_tz.localize(dt_naive, is_dst=None)
        else:
            dt_aware = dt_naive.astimezone(user_tz)
        return dt_aware
    except (ValueError, OverflowError, TypeError) as e:
        logging.getLogger(__name__).warning(f"Could not parse datetime string '{dt_str}': {e}")
        return None


def parse_timedelta_minutes(minutes: Optional[int]) -> Optional[timedelta]:
    """Parses duration in minutes to timedelta."""
    if minutes is None or minutes <= 0:
        return None
    try:
        return timedelta(minutes=int(minutes))
    except (ValueError, TypeError):
        return None