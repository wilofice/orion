import logging
from tool_wrappers import TOOL_REGISTRY
from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class AbstractToolExecutor:
    def execute_tool(self, call, context: ExecutionContext) -> ExecutorToolResult:
        """Execute the requested tool using the provided context."""
        logger.info("Executing tool %s", call.name)

        tool_wrapper = TOOL_REGISTRY.get(call.name)
        if not tool_wrapper:
            logger.error("Tool '%s' not found in registry", call.name)
            return ExecutorToolResult(
                name=call.name,
                status=ToolResultStatus.ERROR,
                error_details=f"Tool '{call.name}' not found.",
            )

        try:
            return tool_wrapper.run(call.args, context)
        except Exception as e:
            logger.exception("Error executing tool '%s'", call.name)
            return ExecutorToolResult(
                name=call.name,
                status=ToolResultStatus.ERROR,
                error_details=f"An error occurred while executing tool '{call.name}': {e}",
            )
