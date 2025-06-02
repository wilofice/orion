# app/db/user_tasks.py

import time
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError
from .base import get_dynamodb_resource
from settings_v1 import settings

# Initialize table reference
user_tasks_table = get_dynamodb_resource().Table(settings.DYNAMODB_USER_TASKS_TABLE_NAME)


def create_user_tasks_table():
    """Creates the user_tasks table if it doesn't exist."""
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_USER_TASKS_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'task_id', 'KeyType': 'RANGE'},  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'task_id', 'AttributeType': 'S'},
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


def save_user_task(user_id: str, task_data: Dict[str, Any]) -> str:
    """
    Saves a user task to DynamoDB.
    
    Args:
        user_id: The user ID
        task_data: Dictionary containing task data (should include task_id)
        
    Returns:
        "success" if successful, error message otherwise
    """
    try:
        # Add timestamps
        current_timestamp = int(time.time())
        task_data['user_id'] = user_id
        task_data['created_at'] = current_timestamp
        task_data['updated_at'] = current_timestamp
        
        # Save to DynamoDB
        user_tasks_table.put_item(Item=task_data)
        print(f"Successfully saved task {task_data['task_id']} for user {user_id}")
        return "success"
    except ClientError as e:
        error_msg = f"Error saving task to DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during task save: {e}"
        print(error_msg)
        return error_msg


def get_user_tasks(user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Retrieves user tasks from DynamoDB with optional filtering.
    
    Args:
        user_id: The user ID
        filters: Optional dictionary with filter criteria
        
    Returns:
        List of tasks matching the criteria
    """
    try:
        # Query all tasks for the user
        response = user_tasks_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={
                ':uid': user_id
            }
        )
        
        tasks = response.get('Items', [])
        
        # Apply filters if provided
        if filters:
            # Filter by category
            if 'category' in filters and filters['category']:
                tasks = [t for t in tasks if t.get('category') == filters['category']]
            
            # Filter by status
            if 'status' in filters and filters['status']:
                tasks = [t for t in tasks if t.get('status') == filters['status']]
            
            # Filter by minimum priority
            if 'priority_min' in filters and filters['priority_min'] is not None:
                tasks = [t for t in tasks if t.get('priority', 0) >= filters['priority_min']]
            
            # Filter by deadline
            if 'due_before' in filters and filters['due_before']:
                due_before_timestamp = filters['due_before']
                tasks = [t for t in tasks if t.get('deadline_timestamp') and t['deadline_timestamp'] <= due_before_timestamp]
        
        print(f"Successfully retrieved {len(tasks)} tasks for user {user_id}")
        return tasks
        
    except ClientError as e:
        print(f"Error retrieving tasks from DynamoDB for {user_id}: {e.response['Error']['Message']}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during task retrieval: {e}")
        return []


def update_user_task(user_id: str, task_id: str, updates: Dict[str, Any]) -> str:
    """
    Updates a specific task.
    
    Args:
        user_id: The user ID
        task_id: The task ID
        updates: Dictionary containing fields to update
        
    Returns:
        "success" if successful, error message otherwise
    """
    try:
        # Build update expression
        update_expr_parts = []
        expr_attr_names = {}
        expr_attr_values = {}
        
        # Add updated_at timestamp
        updates['updated_at'] = int(time.time())
        
        for key, value in updates.items():
            if key not in ['user_id', 'task_id']:  # Don't update keys
                attr_name = f"#{key}"
                attr_value = f":{key}"
                update_expr_parts.append(f"{attr_name} = {attr_value}")
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = value
        
        if not update_expr_parts:
            return "No fields to update"
        
        update_expression = "SET " + ", ".join(update_expr_parts)
        
        # Update the item
        user_tasks_table.update_item(
            Key={'user_id': user_id, 'task_id': task_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        
        print(f"Successfully updated task {task_id} for user {user_id}")
        return "success"
    except ClientError as e:
        error_msg = f"Error updating task in DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during task update: {e}"
        print(error_msg)
        return error_msg


def delete_user_task(user_id: str, task_id: str) -> bool:
    """
    Deletes a user task from DynamoDB.
    
    Args:
        user_id: The user ID
        task_id: The task ID to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        user_tasks_table.delete_item(Key={'user_id': user_id, 'task_id': task_id})
        print(f"Successfully deleted task {task_id} for user {user_id}")
        return True
    except ClientError as e:
        print(f"Error deleting task from DynamoDB: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during task deletion: {e}")
        return False