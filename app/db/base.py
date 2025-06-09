# app/db/base.py

import boto3
from settings_v1 import settings


def get_dynamodb_resource():
    if settings.AWS_DYNAMODB_ENDPOINT_URL:  # For local testing
        print(f"Connecting to DynamoDB Local at {settings.AWS_DYNAMODB_ENDPOINT_URL}")
        return boto3.resource('dynamodb',
                              region_name=settings.AWS_REGION,
                              endpoint_url=settings.AWS_DYNAMODB_ENDPOINT_URL)
    else:  # For AWS environment
        print(f"Connecting to DynamoDB in region {settings.AWS_REGION}")
        return boto3.resource('dynamodb', region_name=settings.AWS_REGION)