# app/tools/get_calendar_analytics.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError, field_validator
import pytz

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult


class GetCalendarAnalyticsWrapperArgs(BaseModel):
    """Input validation model for get_calendar_analytics arguments."""
    days_back: Optional[int] = Field(30, ge=1, le=365, description="Number of days to analyze")
    group_by: Optional[str] = Field("category", description="Group results by: category, day, week")
    include_stats: Optional[List[str]] = Field(
        default_factory=lambda: ["total_time", "meeting_count", "average_duration"],
        description="Statistics to include"
    )
    
    @field_validator('group_by')
    @classmethod
    def check_group_by(cls, v: str):
        """Validate group_by value."""
        valid_options = ["category", "day", "week", "month"]
        if v not in valid_options:
            raise ValueError(f"group_by must be one of: {valid_options}")
        return v


class GetCalendarAnalyticsWrapper(ToolWrapper):
    """
    Wrapper for the 'get_calendar_analytics' tool.
    Analyzes calendar data to provide insights about time usage.
    """
    tool_name = "get_calendar_analytics"
    logger = logging.getLogger(__name__)
    description = "Analyzes calendar events to provide insights about time allocation and meeting patterns."
    parameters_schema = {
        "type": "object",
        "properties": {
            "days_back": {
                "type": "integer",
                "description": "Number of days to analyze (1-365). Default is 30.",
                "minimum": 1,
                "maximum": 365
            },
            "group_by": {
                "type": "string",
                "description": "Group results by: category, day, week, month. Default is category.",
                "enum": ["category", "day", "week", "month"]
            },
            "include_stats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Statistics to include: total_time, meeting_count, average_duration, etc."
            }
        },
        "required": []
    }
    
    def _categorize_event(self, event: Dict[str, Any]) -> str:
        """Categorize an event based on its properties."""
        summary = event.get('summary', '').lower()
        attendees = event.get('attendees', [])
        
        # Simple categorization logic
        if len(attendees) > 1:
            if any(keyword in summary for keyword in ['interview', 'candidate']):
                return "INTERVIEWS"
            elif any(keyword in summary for keyword in ['1:1', 'one-on-one', 'sync']):
                return "ONE_ON_ONES"
            else:
                return "MEETINGS"
        elif any(keyword in summary for keyword in ['focus', 'work', 'deep work']):
            return "FOCUS_TIME"
        elif any(keyword in summary for keyword in ['lunch', 'break', 'coffee']):
            return "BREAKS"
        else:
            return "OTHER"
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetCalendarAnalyticsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid arguments: {e.errors()}")
        
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
            now = datetime.now(user_tz)
            end_time = now
            start_time = now - timedelta(days=validated_args.days_back)
            
            # Get events from calendar
            service = context.calendar_client._get_service()
            
            events_list = []
            page_token = None
            
            while True:
                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=start_time.isoformat(),
                    timeMax=end_time.isoformat(),
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token,
                    maxResults=250
                ).execute()
                
                events = events_result.get('items', [])
                events_list.extend(events)
                
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            
            # Analyze events
            analytics = {
                "total_events": len(events_list),
                "total_hours": 0,
                "by_category": {},
                "by_day": {},
                "busiest_days": [],
                "average_events_per_day": 0,
                "average_meeting_duration": 0
            }
            
            total_duration_minutes = 0
            timed_events = 0
            
            for event in events_list:
                # Skip transparent or cancelled events
                if event.get('transparency') == 'transparent' or event.get('status') == 'cancelled':
                    continue
                
                # Get event duration
                if 'dateTime' in event.get('start', {}):
                    start_dt = datetime.fromisoformat(event['start']['dateTime'])
                    end_dt = datetime.fromisoformat(event['end']['dateTime'])
                    duration_minutes = (end_dt - start_dt).total_seconds() / 60
                    
                    total_duration_minutes += duration_minutes
                    timed_events += 1
                    
                    # Categorize event
                    category = self._categorize_event(event)
                    
                    # Update category stats
                    if category not in analytics["by_category"]:
                        analytics["by_category"][category] = {
                            "count": 0,
                            "total_minutes": 0,
                            "average_duration": 0
                        }
                    
                    analytics["by_category"][category]["count"] += 1
                    analytics["by_category"][category]["total_minutes"] += duration_minutes
                    
                    # Update daily stats
                    day_key = start_dt.date().isoformat()
                    if day_key not in analytics["by_day"]:
                        analytics["by_day"][day_key] = {
                            "count": 0,
                            "total_minutes": 0
                        }
                    
                    analytics["by_day"][day_key]["count"] += 1
                    analytics["by_day"][day_key]["total_minutes"] += duration_minutes
            
            # Calculate aggregates
            analytics["total_hours"] = round(total_duration_minutes / 60, 1)
            analytics["average_meeting_duration"] = round(total_duration_minutes / timed_events, 0) if timed_events > 0 else 0
            analytics["average_events_per_day"] = round(timed_events / validated_args.days_back, 1)
            
            # Calculate category averages
            for category, stats in analytics["by_category"].items():
                if stats["count"] > 0:
                    stats["average_duration"] = round(stats["total_minutes"] / stats["count"], 0)
                    stats["total_hours"] = round(stats["total_minutes"] / 60, 1)
            
            # Find busiest days
            if analytics["by_day"]:
                sorted_days = sorted(
                    analytics["by_day"].items(),
                    key=lambda x: x[1]["total_minutes"],
                    reverse=True
                )[:5]
                
                analytics["busiest_days"] = [
                    {
                        "date": day,
                        "events": stats["count"],
                        "hours": round(stats["total_minutes"] / 60, 1)
                    }
                    for day, stats in sorted_days
                ]
            
            # Format result based on group_by
            if validated_args.group_by == "category":
                primary_grouping = analytics["by_category"]
            elif validated_args.group_by == "day":
                primary_grouping = analytics["by_day"]
            else:
                primary_grouping = analytics["by_category"]
            
            result_data = {
                "message": f"Analyzed {timed_events} events over the past {validated_args.days_back} days",
                "time_period": {
                    "start": start_time.date().isoformat(),
                    "end": end_time.date().isoformat(),
                    "days": validated_args.days_back
                },
                "summary": {
                    "total_events": timed_events,
                    "total_hours": analytics["total_hours"],
                    "average_events_per_day": analytics["average_events_per_day"],
                    "average_meeting_duration_minutes": analytics["average_meeting_duration"]
                },
                "breakdown": primary_grouping,
                "busiest_days": analytics["busiest_days"],
                "insights": []
            }
            
            # Generate insights
            if analytics["total_hours"] > 0:
                meeting_percentage = 0
                if "MEETINGS" in analytics["by_category"]:
                    meeting_percentage = round(
                        (analytics["by_category"]["MEETINGS"]["total_minutes"] / total_duration_minutes) * 100,
                        0
                    )
                    result_data["insights"].append(
                        f"{meeting_percentage}% of your time is spent in meetings"
                    )
                
                if analytics["average_meeting_duration"] > 60:
                    result_data["insights"].append(
                        f"Your average meeting is {int(analytics['average_meeting_duration'])} minutes - consider shorter meetings"
                    )
                
                if analytics["average_events_per_day"] > 6:
                    result_data["insights"].append(
                        "You average more than 6 events per day - consider blocking focus time"
                    )
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error analyzing calendar: {e}")
            return self._create_error_result(f"Failed to analyze calendar: {str(e)}")