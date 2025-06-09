# app/tools/create_task.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator
import pytz

from .base import ToolWrapper, parse_datetime_flexible
from tool_interface import ExecutionContext, ExecutorToolResult
from models import WantToDoActivity, ActivityCategory, ActivityStatus


class CreateTaskWrapperArgs(BaseModel):
    """Input validation model for create_task arguments."""
    title: str = Field(..., description="The title of the task")
    description: Optional[str] = Field(None, description="Task description")
    category_str: str = Field(..., description="Task category (e.g., 'WORK', 'PERSONAL')")
    priority: Optional[int] = Field(5, ge=1, le=10, description="Priority (1-10)")
    deadline_str: Optional[str] = Field(None, description="Optional deadline")
    estimated_duration_minutes: Optional[int] = Field(60, gt=0, description="Estimated duration in minutes")
    
    @field_validator('category_str')
    @classmethod
    def check_category(cls, v: str):
        """Validate category string matches enum values."""
        if v.upper() not in ActivityCategory.__members__:
            raise ValueError(f"Invalid category. Choose from: {list(ActivityCategory.__members__.keys())}")
        return v


class CreateTaskWrapper(ToolWrapper):
    """
    Wrapper for the 'create_task' tool.
    Creates a new task in the user's WantToDo list.
    """
    tool_name = "create_task"
    logger = logging.getLogger(__name__)
    description = "Creates a new task or to-do item with specified details and priority."
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title of the task"
            },
            "description": {
                "type": "string",
                "description": "Optional task description"
            },
            "category_str": {
                "type": "string",
                "description": "Task category (WORK, PERSONAL, LEARNING, EXERCISE, SOCIAL, CHORE, ERRAND, FUN, OTHER)"
            },
            "priority": {
                "type": "integer",
                "description": "Priority level (1-10, higher is more important). Default is 5.",
                "minimum": 1,
                "maximum": 10
            },
            "deadline_str": {
                "type": "string",
                "description": "Optional deadline in timezone-aware format"
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "description": "Estimated duration in minutes. Default is 60.",
                "minimum": 1
            }
        },
        "required": ["title", "category_str"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = CreateTaskWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_clarification_result(
                f"Invalid task details: {e.errors()}",
                result_data={"validation_errors": e.errors()}
            )
        
        # 2. Parse deadline if provided
        deadline = None
        if validated_args.deadline_str:
            try:
                user_tz = pytz.timezone(context.preferences.time_zone)
                deadline = parse_datetime_flexible(validated_args.deadline_str, user_tz)
                if not deadline:
                    return self._create_error_result("Could not parse deadline")
            except Exception as e:
                self.logger.error(f"Error parsing deadline: {e}")
                return self._create_error_result(f"Invalid deadline format: {validated_args.deadline_str}")
        
        # 3. Create WantToDoActivity and save to DynamoDB
        try:
            task = WantToDoActivity(
                title=validated_args.title,
                description=validated_args.description,
                estimated_duration=timedelta(minutes=validated_args.estimated_duration_minutes),
                priority=validated_args.priority,
                category=ActivityCategory(validated_args.category_str.upper()),
                deadline=deadline,
                status=ActivityStatus.TODO
            )
            
            # Import DynamoDB operations
            from dynamodb import save_user_task
            
            # Prepare task data for DynamoDB
            task_data = {
                'task_id': task.id,
                'title': task.title,
                'description': task.description or '',
                'category': task.category.value,
                'priority': task.priority,
                'status': task.status.value,
                'estimated_duration_minutes': validated_args.estimated_duration_minutes
            }
            
            # Add deadline if present
            if deadline:
                task_data['deadline'] = deadline.isoformat()
                task_data['deadline_timestamp'] = int(deadline.timestamp())
            
            # Save to DynamoDB
            save_result = save_user_task(context.user_id, task_data)
            
            if save_result != "success":
                self.logger.error(f"Failed to save task to DynamoDB: {save_result}")
                return self._create_error_result(f"Failed to save task: {save_result}")
            
            self.logger.info(f"Successfully created and saved task '{task.title}' with ID {task.id}")
            
            result_data = {
                "message": f"Successfully created task '{task.title}'",
                "task_id": task.id,
                "title": task.title,
                "description": task.description,
                "category": task.category.value,
                "priority": task.priority,
                "estimated_duration_minutes": validated_args.estimated_duration_minutes,
                "status": task.status.value
            }
            
            if deadline:
                result_data["deadline"] = deadline.isoformat()
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error creating task: {e}")
            return self._create_error_result(f"Failed to create task: {str(e)}")