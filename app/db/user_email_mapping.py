# app/db/user_email_mapping.py

import time
from typing import Optional
from botocore.exceptions import ClientError
from .base import get_dynamodb_resource
from settings_v1 import settings

# Initialize table reference
user_email_mapping_table = get_dynamodb_resource().Table(settings.DYNAMODB_USER_EMAIL_MAPPING_TABLE_NAME)


def create_user_email_mapping_table():
    """Creates the user_email_mapping table if it doesn't exist."""
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_USER_EMAIL_MAPPING_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'email', 'KeyType': 'HASH'},  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'},
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


def save_user_email_mapping(email: str, user_id: str) -> str:
    """
    Saves the mapping between user email and user ID.
    
    Args:
        email: The user's email address
        user_id: The user's ID (GUID)
        
    Returns:
        "success" if successful, error message otherwise
    """
    try:
        current_timestamp = int(time.time())
        item = {
            'email': email.lower(),  # Store email in lowercase for consistency
            'user_id': user_id,
            'created_at': current_timestamp,
            'updated_at': current_timestamp
        }
        
        user_email_mapping_table.put_item(Item=item)
        print(f"Successfully saved email mapping for {email} -> {user_id}")
        return "success"
    except ClientError as e:
        error_msg = f"Error saving email mapping to DynamoDB: {e.response['Error']['Message']}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during email mapping save: {e}"
        print(error_msg)
        return error_msg


def get_user_id_by_email(email: str) -> Optional[str]:
    """
    Retrieves the user ID for a given email address.
    
    Args:
        email: The user's email address
        
    Returns:
        The user ID if found, None otherwise
    """
    try:
        response = user_email_mapping_table.get_item(Key={'email': email.lower()})
        if 'Item' not in response:
            print(f"No user ID found for email: {email}")
            return None
        
        user_id = response['Item']['user_id']
        print(f"Successfully retrieved user ID for email {email}: {user_id}")
        return user_id
    except ClientError as e:
        print(f"Error retrieving user ID from DynamoDB for {email}: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during user ID retrieval: {e}")
        return None


def delete_user_email_mapping(email: str) -> bool:
    """
    Deletes the email to user ID mapping.
    
    Args:
        email: The user's email address
        
    Returns:
        True if successful, False otherwise
    """
    try:
        user_email_mapping_table.delete_item(Key={'email': email.lower()})
        print(f"Successfully deleted email mapping for {email}")
        return True
    except ClientError as e:
        print(f"Error deleting email mapping from DynamoDB: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during email mapping deletion: {e}")
        return False