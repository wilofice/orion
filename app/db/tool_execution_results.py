# app/db/tool_execution_results.py

import time
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError
from .base import get_dynamodb_resource
from settings_v1 import settings

# Initialize table reference
tool_execution_results_table = get_dynamodb_resource().Table(settings.DYNAMODB_TOOL_EXECUTION_RESULTS_TABLE_NAME)


def create_tool_execution_results_table():
    """Creates the tool_execution_results table if it doesn't exist."""
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_TOOL_EXECUTION_RESULTS_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'session_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'execution_id', 'KeyType': 'RANGE'},  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'session_id', 'AttributeType': 'S'},
                {'AttributeName': 'execution_id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'N'},
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'user_id-timestamp-index',
                    'KeySchema': [
                        {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5,
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5,
            }
        )
        table.wait_until_exists()
        print(f"Table {table_name} created successfully.")
    except Exception as e:
        print(f"Error creating table {table_name}: {e}")


def save_tool_execution_result(
    session_id: str,
    execution_id: str,
    user_id: str,
    tool_name: str,
    function_call: Dict[str, Any],
    execution_result: Dict[str, Any],
    status: str,
    error_details: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> str:
    """
    Saves a tool execution result to DynamoDB.
    
    Args:
        session_id: The chat session ID
        execution_id: Unique ID for this execution
        user_id: The user ID
        tool_name: Name of the tool that was executed
        function_call: The function call details (name and args)
        execution_result: The result of the execution
        status: The execution status (success, error, clarification_needed)
        error_details: Error details if status is error
        duration_ms: Execution duration in milliseconds
        
    Returns:
        "success" if successful, error message otherwise
    """
    try:
        current_timestamp = int(time.time())
        item = {
            'session_id': session_id,
            'execution_id': execution_id,
            'user_id': user_id,
            'timestamp': current_timestamp,
            'tool_name': tool_name,
            'function_call': function_call,
            'execution_result': execution_result,
            'status': status,
            'created_at': current_timestamp
        }
        
        if error_details:
            item['error_details'] = error_details
        if duration_ms is not None:
            item['duration_ms'] = duration_ms
        
        tool_execution_results_table.put_item(Item=item)
        print(f"Successfully saved tool execution result for {tool_name} in session {session_id}")
        return "success"
    except ClientError as e:
        error_msg = f"Error saving tool execution result to DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during tool execution result save: {e}"
        print(error_msg)
        return error_msg


def get_tool_execution_results_by_session(session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all tool execution results for a specific session.
    
    Args:
        session_id: The chat session ID
        
    Returns:
        List of tool execution results sorted by timestamp
    """
    try:
        response = tool_execution_results_table.query(
            KeyConditionExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id}
        )
        
        results = response.get('Items', [])
        # Sort by timestamp (should already be sorted by execution_id, but making sure)
        results.sort(key=lambda x: x.get('timestamp', 0))
        
        print(f"Successfully retrieved {len(results)} tool execution results for session {session_id}")
        return results
    except ClientError as e:
        print(f"Error retrieving tool execution results from DynamoDB: {e.response['Error']['Message']}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during tool execution results retrieval: {e}")
        return []


def get_tool_execution_results_by_user(
    user_id: str, 
    start_timestamp: Optional[int] = None,
    end_timestamp: Optional[int] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves tool execution results for a specific user within a time range.
    
    Args:
        user_id: The user ID
        start_timestamp: Start timestamp (inclusive)
        end_timestamp: End timestamp (inclusive)
        limit: Maximum number of results to return
        
    Returns:
        List of tool execution results sorted by timestamp
    """
    try:
        # Build the query parameters
        key_condition_expression = 'user_id = :uid'
        expression_attribute_values = {':uid': user_id}
        
        if start_timestamp and end_timestamp:
            key_condition_expression += ' AND #ts BETWEEN :start AND :end'
            expression_attribute_values[':start'] = start_timestamp
            expression_attribute_values[':end'] = end_timestamp
        elif start_timestamp:
            key_condition_expression += ' AND #ts >= :start'
            expression_attribute_values[':start'] = start_timestamp
        elif end_timestamp:
            key_condition_expression += ' AND #ts <= :end'
            expression_attribute_values[':end'] = end_timestamp
        
        query_params = {
            'IndexName': 'user_id-timestamp-index',
            'KeyConditionExpression': key_condition_expression,
            'ExpressionAttributeValues': expression_attribute_values,
            'ExpressionAttributeNames': {'#ts': 'timestamp'}
        }
        
        if limit:
            query_params['Limit'] = limit
        
        response = tool_execution_results_table.query(**query_params)
        
        results = response.get('Items', [])
        print(f"Successfully retrieved {len(results)} tool execution results for user {user_id}")
        return results
    except ClientError as e:
        print(f"Error retrieving tool execution results from DynamoDB: {e.response['Error']['Message']}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during tool execution results retrieval: {e}")
        return []


def get_tool_execution_statistics(user_id: str) -> Dict[str, Any]:
    """
    Gets statistics about tool executions for a user.
    
    Args:
        user_id: The user ID
        
    Returns:
        Dictionary with statistics including tool usage counts, success rates, etc.
    """
    try:
        # Get all results for the user
        results = get_tool_execution_results_by_user(user_id)
        
        if not results:
            return {
                'total_executions': 0,
                'tools_used': {},
                'success_rate': 0.0,
                'average_duration_ms': 0
            }
        
        # Calculate statistics
        total = len(results)
        success_count = sum(1 for r in results if r.get('status') == 'success')
        tools_count = {}
        total_duration = 0
        duration_count = 0
        
        for result in results:
            tool_name = result.get('tool_name', 'unknown')
            tools_count[tool_name] = tools_count.get(tool_name, 0) + 1
            
            if 'duration_ms' in result:
                total_duration += result['duration_ms']
                duration_count += 1
        
        avg_duration = total_duration / duration_count if duration_count > 0 else 0
        
        return {
            'total_executions': total,
            'tools_used': tools_count,
            'success_rate': (success_count / total) * 100 if total > 0 else 0.0,
            'success_count': success_count,
            'error_count': total - success_count,
            'average_duration_ms': avg_duration
        }
    except Exception as e:
        print(f"Error calculating tool execution statistics: {e}")
        return {
            'total_executions': 0,
            'tools_used': {},
            'success_rate': 0.0,
            'average_duration_ms': 0,
            'error': str(e)
        }