# app/db/chat_sessions.py

from typing import List, Dict, Any
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from .base import get_dynamodb_resource
from settings_v1 import settings

# Initialize table reference
chat_sessions_table = get_dynamodb_resource().Table(settings.DYNAMODB_CHAT_SESSIONS_TABLE_NAME)


def create_chat_sessions_table():
    """Creates the chat_sessions table if it doesn't exist."""
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_CHAT_SESSIONS_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5,
            },
        )
        table.wait_until_exists()
        print(f"Table {table_name} created successfully.")
    except Exception as e:
        print(f"Error creating table {table_name}: {e}")


def get_user_conversations(user_id: str) -> List[Dict[str, Any]]:
    """Return all chat sessions for the given user from DynamoDB."""
    try:
        response = chat_sessions_table.scan(
            FilterExpression=Attr("user_id").eq(user_id)
        )
        return response.get("Items", [])
    except ClientError as e:
        print(
            f"Error retrieving conversations for {user_id}: {e.response['Error']['Message']}"
        )
        return []
    except Exception as e:
        print(f"An unexpected error occurred during conversation retrieval: {e}")
        return []