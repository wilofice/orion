# app/db/user_preferences.py

import time
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError
from .base import get_dynamodb_resource
from settings_v1 import settings

# Initialize table reference
user_preferences_table = get_dynamodb_resource().Table(settings.DYNAMODB_USER_PREFERENCES_TABLE_NAME)


def create_user_preferences_table():
    """Creates the user_preferences table if it doesn't exist."""
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_USER_PREFERENCES_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
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


def save_user_preferences(preferences_dict: Dict[str, Any]) -> str:
    """
    Saves user preferences to DynamoDB.
    
    Args:
        preferences_dict: Dictionary containing user preferences including user_id
        
    Returns:
        "success" if successful, error message otherwise
    """
    try:
        # Add timestamp
        current_timestamp = int(time.time())
        preferences_dict['updated_at'] = current_timestamp
        
        # Check if this is a new record
        existing = get_user_preferences(preferences_dict['user_id'])
        if not existing:
            preferences_dict['created_at'] = current_timestamp
        else:
            # Preserve created_at from existing record
            preferences_dict['created_at'] = existing.get('created_at', current_timestamp)
        
        # Save to DynamoDB
        user_preferences_table.put_item(Item=preferences_dict)
        print(f"Successfully saved preferences for user_id: {preferences_dict['user_id']}")
        return "success"
    except ClientError as e:
        error_msg = f"Error saving preferences to DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during preferences save: {e}"
        print(error_msg)
        return error_msg


def get_user_preferences(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves user preferences from DynamoDB.
    
    Args:
        user_id: The user ID to retrieve preferences for
        
    Returns:
        Dictionary containing user preferences or None if not found
    """
    try:
        response = user_preferences_table.get_item(Key={'user_id': user_id})
        if 'Item' not in response:
            print(f"No preferences found for user_id: {user_id}")
            return None
        
        print(f"Successfully retrieved preferences for user_id: {user_id}")
        return response['Item']
    except ClientError as e:
        print(f"Error retrieving preferences from DynamoDB for {user_id}: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during preferences retrieval: {e}")
        return None


def update_user_preferences(user_id: str, updates: Dict[str, Any]) -> str:
    """
    Updates specific fields in user preferences.
    
    Args:
        user_id: The user ID to update preferences for
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
            if key != 'user_id':  # Don't update the primary key
                # Use attribute names to handle reserved keywords
                attr_name = f"#{key}"
                attr_value = f":{key}"
                update_expr_parts.append(f"{attr_name} = {attr_value}")
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = value
        
        if not update_expr_parts:
            return "No fields to update"
        
        update_expression = "SET " + ", ".join(update_expr_parts)
        
        # Update the item
        user_preferences_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        
        print(f"Successfully updated preferences for user_id: {user_id}")
        return "success"
    except ClientError as e:
        error_msg = f"Error updating preferences in DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during preferences update: {e}"
        print(error_msg)
        return error_msg


def delete_user_preferences(user_id: str) -> bool:
    """
    Deletes user preferences from DynamoDB.
    
    Args:
        user_id: The user ID to delete preferences for
        
    Returns:
        True if successful, False otherwise
    """
    try:
        user_preferences_table.delete_item(Key={'user_id': user_id})
        print(f"Successfully deleted preferences for user_id: {user_id}")
        return True
    except ClientError as e:
        print(f"Error deleting preferences from DynamoDB for {user_id}: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during preferences deletion: {e}")
        return False