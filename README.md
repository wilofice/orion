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
