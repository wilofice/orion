# ChatService and Backend API Interaction Documentation

## Overview

The `ChatService` class (`lib/src/services/chat_service.dart`) serves as the primary interface between the Flutter frontend and the backend API for all chat-related operations. It handles message sending, conversation retrieval, authentication, and error management.

## Architecture

### Key Components

1. **ChatService**: The main service class that manages HTTP communication
2. **Data Models**: Strongly-typed classes that match backend schemas
3. **Error Handling**: Comprehensive error management with custom error types
4. **Authentication**: Integration with AuthProvider for token management

## API Endpoints

### 1. Send Message Endpoint
- **URL**: `{backendApiBaseUrl}/chat/prompt`
- **Method**: POST
- **Purpose**: Send user messages (text or voice) to the AI assistant

### 2. Fetch Conversations Endpoint
- **URL**: `{backendApiBaseUrl}/conversations/{userId}`
- **Method**: GET
- **Purpose**: Retrieve conversation history for a specific user

## Data Models

### Request Models

#### ChatRequestData
Matches the backend `ChatRequest` schema:
```dart
{
  "user_id": String (required),
  "prompt_text": String (required),
  "session_id": String? (optional),
  "audio_url": String? (optional),
  "client_context": Map<String, dynamic>? (optional)
}
```

**Field Descriptions**:
- `user_id`: Unique identifier for the user
- `prompt_text`: The text message or transcribed audio content
- `session_id`: Maintains conversation continuity
- `audio_url`: S3 URL for voice messages
- `client_context`: Additional metadata (e.g., timezone, current view)

### Response Models

#### ChatResponseData
Matches the backend `ChatResponse` schema:
```dart
{
  "session_id": String,
  "status": String ("completed" | "needs_clarification" | "error"),
  "response_text": String?,
  "clarification_options": List<String>?
}
```

**Status Values**:
- `completed`: Request processed successfully
- `needs_clarification`: AI needs more information
- `error`: Processing failed

#### ConversationData
Represents a complete conversation:
```dart
{
  "session_id": String,
  "user_id": String,
  "history": List<ConversationTurnData>
}
```

#### ConversationTurnData
Individual message in a conversation:
```dart
{
  "role": String ("user" | "assistant"),
  "parts": List<dynamic>,
  "timestamp": DateTime?
}
```

**Parts Structure**:
- For text messages: `["message text"]`
- For audio messages: `[{"transcript": "text", "audio_url": "https://s3..."}]`

## Message Flow

### Sending a Message

1. **Authentication Check**
   ```dart
   final token = _authProvider.backendAccessToken;
   if (token == null) throw ChatServiceError('Not authenticated');
   ```

2. **Request Preparation**
   - Creates `ChatRequestData` object
   - Includes user ID from auth provider
   - Adds optional audio URL for voice messages
   - Includes client context if provided

3. **HTTP Request**
   ```dart
   headers: {
     'Content-Type': 'application/json; charset=UTF-8',
     'Authorization': 'Bearer $token',
     'Accept': 'application/json'
   }
   ```

4. **Response Handling**
   - Success (200-299): Parses `ChatResponseData`
   - Error: Extracts `ApiErrorDetail` and throws `ChatServiceError`

### Voice Message Flow

1. **Recording**: Audio recorded locally using `AudioRecorderService`
2. **Transcription**: Speech-to-text conversion using `SpeechService`
3. **Upload**: Audio file uploaded to S3 via `AudioUploadService`
4. **Send**: Both transcript and S3 URL sent to backend
5. **Storage**: Backend stores audio URL with conversation
6. **Retrieval**: Audio URL returned when fetching conversation history
7. **Playback**: Frontend plays audio from S3 URL using `AudioPlayerWidget`

## Error Handling

### ChatServiceError
Custom error class with structured information:
```dart
{
  message: String,
  statusCode: int?,
  errorCode: String?,
  errorDetails: Map<String, dynamic>?
}
```

### Common Error Codes
- `NO_BACKEND_TOKEN`: User not authenticated
- `NETWORK_ERROR`: Network connectivity issues
- `UNEXPECTED_ERROR`: Parsing or unknown errors

### Error Response Format
Backend errors follow the `ErrorDetail` schema:
```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Invalid request format",
  "details": { "field": "prompt_text", "reason": "empty" }
}
```

## Authentication Flow

1. **Token Management**:
   - Backend token stored in `AuthProvider`
   - Automatically included in all API requests
   - Token obtained during Google OAuth flow

2. **Unauthorized Handling**:
   - 401 responses trigger re-authentication
   - User redirected to login screen
   - Session state cleared

## Usage Examples

### Sending a Text Message
```dart
final response = await chatService.sendMessage(
  promptText: "What's the weather today?",
  sessionId: currentSessionId,
  userId: authProvider.userId!,
  clientContext: {"timezone": "UTC-5"}
);
```

### Sending a Voice Message
```dart
final response = await chatService.sendMessage(
  promptText: transcribedText,
  audioUrl: "https://s3.../audio.m4a",
  sessionId: currentSessionId,
  userId: authProvider.userId!,
);
```

### Fetching Conversation History
```dart
final conversations = await chatService.fetchConversations(
  userId: authProvider.userId!
);

// Process audio messages
for (var turn in conversation.history) {
  if (turn.parts.first is Map) {
    final audioUrl = turn.parts.first['audio_url'];
    final transcript = turn.parts.first['transcript'];
  }
}
```

## Security Considerations

1. **Token Security**:
   - Bearer tokens sent in Authorization header
   - Tokens never logged in production
   - Automatic token refresh on expiry

2. **Data Privacy**:
   - Audio files stored in user-specific S3 paths
   - URLs use secure HTTPS protocol
   - Client context sanitized before sending

3. **Error Handling**:
   - Sensitive information removed from error messages
   - Stack traces only logged in debug mode
   - User-friendly error messages displayed

## Testing Recommendations

1. **Unit Tests**:
   - Mock HTTP client for request/response testing
   - Test all error scenarios
   - Verify data model serialization

2. **Integration Tests**:
   - Test with real backend (staging environment)
   - Verify audio upload and retrieval flow
   - Test session continuity

3. **Error Scenarios**:
   - Network failures
   - Invalid tokens
   - Malformed responses
   - S3 upload failures

## Future Enhancements

1. **Offline Support**:
   - Queue messages when offline
   - Sync when connection restored

2. **Streaming Responses**:
   - Support for real-time AI responses
   - Progressive text rendering

3. **Retry Logic**:
   - Automatic retry for transient failures
   - Exponential backoff strategy

4. **Response Caching**:
   - Cache recent conversations
   - Reduce API calls on app restart