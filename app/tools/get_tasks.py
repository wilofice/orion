# app/tools/get_tasks.py

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError, field_validator
import pytz

from .base import ToolWrapper, parse_datetime_flexible
from tool_interface import ExecutionContext, ExecutorToolResult
from models import ActivityCategory, ActivityStatus


class GetTasksWrapperArgs(BaseModel):
    """Input validation model for get_tasks arguments."""
    category_str: Optional[str] = Field(None, description="Filter by category")
    priority_min: Optional[int] = Field(None, ge=1, le=10, description="Minimum priority")
    status_str: Optional[str] = Field(None, description="Filter by status (TODO, SCHEDULED, DONE)")
    due_before_str: Optional[str] = Field(None, description="Show tasks due before this date")
    limit: Optional[int] = Field(50, ge=1, le=100, description="Maximum number of tasks to return")
    
    @field_validator('category_str')
    @classmethod
    def check_category(cls, v: Optional[str]):
        """Validate category if provided."""
        if v and v.upper() not in ActivityCategory.__members__:
            raise ValueError(f"Invalid category. Choose from: {list(ActivityCategory.__members__.keys())}")
        return v
    
    @field_validator('status_str')
    @classmethod
    def check_status(cls, v: Optional[str]):
        """Validate status if provided."""
        if v and v.upper() not in ActivityStatus.__members__:
            raise ValueError(f"Invalid status. Choose from: {list(ActivityStatus.__members__.keys())}")
        return v


class GetTasksWrapper(ToolWrapper):
    """
    Wrapper for the 'get_tasks' tool.
    Retrieves tasks from the user's WantToDo list with optional filters.
    """
    tool_name = "get_tasks"
    logger = logging.getLogger(__name__)
    description = "Retrieves pending tasks or to-do items with optional filtering by category, priority, or deadline."
    parameters_schema = {
        "type": "object",
        "properties": {
            "category_str": {
                "type": "string",
                "description": "Filter by category (WORK, PERSONAL, LEARNING, etc.)"
            },
            "priority_min": {
                "type": "integer",
                "description": "Show only tasks with priority >= this value (1-10)",
                "minimum": 1,
                "maximum": 10
            },
            "status_str": {
                "type": "string",
                "description": "Filter by status (TODO, SCHEDULED, DONE)"
            },
            "due_before_str": {
                "type": "string",
                "description": "Show only tasks due before this date"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of tasks to return (1-100). Default is 50.",
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": []
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetTasksWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid filter parameters: {e.errors()}")
        
        # 2. Parse due_before date if provided
        due_before = None
        if validated_args.due_before_str:
            try:
                user_tz = pytz.timezone(context.preferences.time_zone)
                due_before = parse_datetime_flexible(validated_args.due_before_str, user_tz)
                if not due_before:
                    return self._create_error_result("Could not parse due_before date")
            except Exception:
                return self._create_error_result(f"Invalid date format: {validated_args.due_before_str}")
        
        try:
            # Import DynamoDB operations
            from dynamodb import get_user_tasks
            
            # Prepare filters for DynamoDB query
            filters = {}
            
            if validated_args.category_str:
                filters['category'] = validated_args.category_str.upper()
            
            if validated_args.priority_min:
                filters['priority_min'] = validated_args.priority_min
            
            if validated_args.status_str:
                filters['status'] = validated_args.status_str.upper()
            
            if due_before:
                filters['due_before'] = int(due_before.timestamp())
            
            # Fetch tasks from DynamoDB
            db_tasks = get_user_tasks(context.user_id, filters)
            
            # Sort by priority (descending) and deadline
            db_tasks.sort(key=lambda t: (
                -t.get('priority', 0),
                t.get('deadline_timestamp', float('inf'))
            ))
            
            # Apply limit
            db_tasks = db_tasks[:validated_args.limit]
            
            # 4. Format response
            tasks_data = []
            for task in db_tasks:
                task_info = {
                    "task_id": task['task_id'],
                    "title": task['title'],
                    "description": task.get('description', ''),
                    "category": task['category'],
                    "priority": task['priority'],
                    "status": task['status'],
                    "estimated_duration_minutes": task.get('estimated_duration_minutes', 60)
                }
                
                # Add deadline if present
                if 'deadline' in task:
                    task_info["deadline"] = task['deadline']
                    # Parse deadline for human-readable format
                    try:
                        deadline_dt = datetime.fromisoformat(task['deadline'])
                        task_info["deadline_human"] = deadline_dt.strftime("%A, %B %d at %I:%M %p")
                    except:
                        task_info["deadline_human"] = task['deadline']
                
                # Add timestamps
                if 'created_at' in task:
                    task_info["created_at"] = task['created_at']
                if 'updated_at' in task:
                    task_info["updated_at"] = task['updated_at']
                
                tasks_data.append(task_info)
            
            # Group by status for summary
            status_counts = {}
            for task in db_tasks:
                status = task.get('status', 'TODO')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            result_data = {
                "message": f"Found {len(db_tasks)} task(s) matching your criteria",
                "task_count": len(db_tasks),
                "status_summary": status_counts,
                "tasks": tasks_data,
                "filters_applied": {
                    "category": validated_args.category_str,
                    "priority_min": validated_args.priority_min,
                    "status": validated_args.status_str,
                    "due_before": due_before.isoformat() if due_before else None
                }
            }
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error retrieving tasks: {e}")
            return self._create_error_result(f"Failed to retrieve tasks: {str(e)}")