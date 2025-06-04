# Orion Backend

This project provides the backend services for the Orion chat assistant.

## DynamoDB Tables

Two DynamoDB tables are used by default:

- `UserGoogleTokens` – stores encrypted Google OAuth tokens.
- `ChatSessions` – stores chat session history.

`ChatSessions` can be created with the helper `create_chat_sessions_table` in
`app/dynamodb.py`.

## Session Management

`DynamoSessionManager` (defined in `app/session_manager.py`) uses the
`ChatSessions` table to persist conversation history. It is now the default
session manager returned by `get_session_manager` in `app/chat_router.py`.

## Conversation History Endpoint

`GET /Prod/conversations/{user_id}` returns all chat sessions for the given user
as a list of `Conversation` objects.

## Architecture Overview

The application is built with **FastAPI**. `app/boot.py` creates the `FastAPI`
instance, configures CORS and logging and registers the following routers:

- **auth_router** – Google OAuth integration and JWT authentication
- **chat_router** – main chat endpoint delegating to the orchestration service
- **conversation_router** – access to stored conversation history
- **events_router** – Google Calendar event queries
- **user_preferences_router** – CRUD operations for scheduling preferences

`lambda_handler` in `app/boot.py` exposes the API for AWS Lambda deployments.

### Orchestration

`app/orchestration_service.py` implements the logic behind the `/chat/prompt`
endpoint. It interacts with a session manager backed by DynamoDB, a Gemini API
client and a registry of tool wrappers used to manipulate calendar data.

### Testing

The `tests/` directory contains unit tests that mock dependencies and verify the
behaviour of routers and the orchestration service.

## Possible Improvements

- Replace stub Gemini and tool executor implementations with real services.
- Use dependency injection throughout to simplify configuration and testing.
- Implement asynchronous calendar operations to improve throughput.
- Persist user preferences and tool execution results in dedicated tables.

## Docker Setup: docker-compose up -d --build