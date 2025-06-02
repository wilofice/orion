# app/tools/get_available_slots.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError
import pytz

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult
from models import TimeSlot


class GetAvailableSlotsWrapperArgs(BaseModel):
    """Input validation model for get_available_slots arguments."""
    days: Optional[int] = Field(7, ge=1, le=30, description="Number of days to look ahead (1-30)")
    min_duration_minutes: Optional[int] = Field(30, ge=15, le=480, description="Minimum slot duration in minutes (15-480)")
    preferred_times_only: Optional[bool] = Field(False, description="Whether to show only slots during preferred meeting times")
    include_weekends: Optional[bool] = Field(True, description="Whether to include weekend slots")
    

class GetAvailableSlotsWrapper(ToolWrapper):
    """
    Wrapper for the 'get_available_slots' tool.
    Retrieves available time slots from the user's calendar considering their preferences.
    """
    tool_name = "get_available_slots"
    logger = logging.getLogger(__name__)
    description = "Finds available (free) time slots in the user's calendar based on their preferences and existing events."
    parameters_schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead for available slots (1-30). Default is 7.",
                "minimum": 1,
                "maximum": 30
            },
            "min_duration_minutes": {
                "type": "integer",
                "description": "Minimum duration for available slots in minutes (15-480). Default is 30.",
                "minimum": 15,
                "maximum": 480
            },
            "preferred_times_only": {
                "type": "boolean",
                "description": "Show only slots during user's preferred meeting times. Default is false."
            },
            "include_weekends": {
                "type": "boolean",
                "description": "Whether to include slots on weekends. Default is true."
            }
        },
        "required": []
    }
    
    def _filter_slots_by_duration(self, slots: List[TimeSlot], min_duration: timedelta) -> List[TimeSlot]:
        """Filter slots to only include those that meet minimum duration."""
        return [slot for slot in slots if slot.duration >= min_duration]
    
    def _filter_slots_by_weekends(self, slots: List[TimeSlot], include_weekends: bool) -> List[TimeSlot]:
        """Filter slots based on weekend preference."""
        if include_weekends:
            return slots
        return [slot for slot in slots if slot.start_time.weekday() < 5]
    
    def _group_slots_by_day(self, slots: List[TimeSlot]) -> Dict[str, List[TimeSlot]]:
        """Group slots by date for easier presentation."""
        grouped = {}
        for slot in slots:
            date_key = slot.start_time.date().isoformat()
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(slot)
        return grouped
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        try:
            validated_args = GetAvailableSlotsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments for finding available slots: {e.errors()}"
            return self._create_error_result(error_msg)
        
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
            self.logger.error(f"Invalid timezone in user preferences: {context.preferences.time_zone} - {e}")
            return self._create_error_result(f"Invalid timezone configuration: {context.preferences.time_zone}")
        
        now = datetime.now(user_tz)
        start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        end_time = start_time + timedelta(days=validated_args.days)
        
        try:
            self.logger.info(f"Fetching available slots from {start_time} to {end_time}")
            
            if validated_args.preferred_times_only:
                temp_preferences = context.preferences
            else:
                temp_preferences = context.preferences
            
            available_slots = context.calendar_client.get_available_time_slots(
                preferences=temp_preferences,
                calendar_id='primary',
                start_time=start_time,
                end_time=end_time
            )
            
            self.logger.info(f"Found {len(available_slots)} raw available slots")
            
            min_duration = timedelta(minutes=validated_args.min_duration_minutes)
            filtered_slots = self._filter_slots_by_duration(available_slots, min_duration)
            filtered_slots = self._filter_slots_by_weekends(filtered_slots, validated_args.include_weekends)
            
            if validated_args.preferred_times_only and context.preferences.preferred_meeting_times:
                preferred_filtered = []
                for slot in filtered_slots:
                    slot_start_time = slot.start_time.time()
                    slot_end_time = slot.end_time.time()
                    
                    for pref_start, pref_end in context.preferences.preferred_meeting_times:
                        if (slot_start_time >= pref_start and slot_end_time <= pref_end):
                            preferred_filtered.append(slot)
                            break
                filtered_slots = preferred_filtered
            
            self.logger.info(f"After filtering: {len(filtered_slots)} available slots")
            
            grouped_slots = self._group_slots_by_day(filtered_slots)
            
            formatted_slots = []
            summary_by_day = {}
            
            for date_str, day_slots in sorted(grouped_slots.items()):
                day_date = datetime.fromisoformat(date_str).date()
                day_name = day_date.strftime("%A")
                
                summary_by_day[date_str] = {
                    "date": date_str,
                    "day_name": day_name,
                    "slot_count": len(day_slots),
                    "total_available_hours": sum(slot.duration.total_seconds() / 3600 for slot in day_slots)
                }
                
                for slot in sorted(day_slots, key=lambda s: s.start_time):
                    formatted_slots.append({
                        "date": date_str,
                        "day_name": day_name,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                        "start_time_local": slot.start_time.strftime("%I:%M %p"),
                        "end_time_local": slot.end_time.strftime("%I:%M %p"),
                        "duration_minutes": int(slot.duration.total_seconds() / 60),
                        "duration_hours": round(slot.duration.total_seconds() / 3600, 1)
                    })
            
            total_slots = len(filtered_slots)
            total_available_hours = sum(slot.duration.total_seconds() / 3600 for slot in filtered_slots)
            
            result_data = {
                "message": f"Found {total_slots} available time slots in the next {validated_args.days} days.",
                "summary": {
                    "total_slots": total_slots,
                    "total_available_hours": round(total_available_hours, 1),
                    "days_checked": validated_args.days,
                    "min_slot_duration_minutes": validated_args.min_duration_minutes,
                    "filters_applied": {
                        "preferred_times_only": validated_args.preferred_times_only,
                        "include_weekends": validated_args.include_weekends
                    }
                },
                "slots_by_day": summary_by_day,
                "available_slots": formatted_slots,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "timezone": context.preferences.time_zone
                }
            }
            
            if total_slots == 0:
                result_data["message"] = f"No available time slots found in the next {validated_args.days} days with the specified criteria."
                result_data["suggestions"] = [
                    "Try increasing the number of days to search",
                    "Reduce the minimum duration requirement",
                    "Include weekends if not already included",
                    "Disable 'preferred times only' filter if enabled"
                ]
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error retrieving available slots: {e}")
            return self._create_error_result(f"Failed to retrieve available slots: {str(e)}")