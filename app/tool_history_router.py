import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from core.security import verify_token
from db import (
    get_tool_execution_results_by_session,
    get_tool_execution_results_by_user,
    get_tool_execution_statistics
)

router = APIRouter(
    prefix="/tool-history",
    tags=["Tool History"],
)


class ToolExecutionResult(BaseModel):
    session_id: str
    execution_id: str
    user_id: str
    timestamp: int
    tool_name: str
    function_call: Dict[str, Any]
    execution_result: Dict[str, Any]
    status: str
    error_details: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: int


class ToolExecutionStatistics(BaseModel):
    total_executions: int
    tools_used: Dict[str, int]
    success_rate: float
    success_count: int
    error_count: int
    average_duration_ms: float


@router.get("/session/{session_id}", response_model=List[ToolExecutionResult])
async def get_session_tool_history(
    session_id: str,
    current_user_id: str = Depends(verify_token)
):
    """Get all tool execution results for a specific session."""
    try:
        # Get the results
        results = get_tool_execution_results_by_session(session_id)
        
        # Verify that all results belong to the current user
        for result in results:
            if result.get('user_id') != current_user_id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only access your own tool execution history"
                )
        
        return results
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Failed to retrieve tool execution history")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve tool execution history"
        ) from exc


@router.get("/user", response_model=List[ToolExecutionResult])
async def get_user_tool_history(
    current_user_id: str = Depends(verify_token),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering results"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering results"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum number of results to return")
):
    """Get tool execution history for the current user within a date range."""
    try:
        # Convert dates to timestamps
        start_timestamp = int(start_date.timestamp()) if start_date else None
        end_timestamp = int(end_date.timestamp()) if end_date else None
        
        # Get the results
        results = get_tool_execution_results_by_user(
            user_id=current_user_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit
        )
        
        return results
    except Exception as exc:
        logging.exception("Failed to retrieve user tool execution history")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve user tool execution history"
        ) from exc


@router.get("/statistics", response_model=ToolExecutionStatistics)
async def get_tool_statistics(
    current_user_id: str = Depends(verify_token)
):
    """Get statistics about tool usage for the current user."""
    try:
        stats = get_tool_execution_statistics(current_user_id)
        
        if 'error' in stats:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate statistics: {stats['error']}"
            )
        
        return ToolExecutionStatistics(**stats)
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception("Failed to retrieve tool execution statistics")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve tool execution statistics"
        ) from exc