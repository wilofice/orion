# PreferenceService and Backend API Interaction Documentation

## Overview

The `PreferenceService` class (`lib/src/services/preference_service.dart`) manages user preferences synchronization between the Flutter frontend and the backend API. It implements a robust caching strategy with offline support and seamless data synchronization.

## Architecture

### Key Components

1. **PreferenceService**: Main service class for preference management
2. **UserPreferences**: Data model representing user preferences
3. **CacheService**: Local storage for offline access
4. **ConnectivityService**: Network status monitoring
5. **AuthProvider**: Authentication and user identity management

## API Endpoint

### Preferences Endpoint
- **URL Pattern**: `{backendApiBaseUrl}/preferences/{userId}`
- **Methods**: GET, POST
- **Authentication**: Bearer token required
- **Purpose**: Retrieve and update user preferences

## Data Models

### UserPreferences Model

The `UserPreferences` class represents the complete set of user preferences with the following structure:

#### Core Fields (Backend-synchronized)
```dart
{
  "user_id": String,
  "time_zone": String,
  "working_hours": Map<String, TimeWindow>,
  "preferred_meeting_times": List<TimeWindow>,
  "days_off": List<String>,
  "preferred_break_duration_minutes": int,
  "work_block_max_duration_minutes": int,
  "input_mode": String ("text" | "voice" | "both"),
  "voice_button_position": String ("left" | "right")
}
```

#### Local-only Fields
```dart
{
  "created_at": int (timestamp),
  "updated_at": int (timestamp),
  "darkMode": bool
}
```

### TimeWindow Model

Represents a time range with start and end times:
```dart
{
  "start": String (HH:MM format),
  "end": String (HH:MM format)
}
```

### Enumerations

#### InputMode
- `text`: Text-only input
- `voice`: Voice-only input
- `both`: Both text and voice input options

#### VoiceButtonPosition
- `left`: Voice button on the left side
- `right`: Voice button on the right side

## API Operations

### 1. Get Preferences (GET)

**Request:**
```http
GET /preferences/{userId}
Authorization: Bearer {token}
Accept: application/json
```

**Response (200 OK):**
```json
{
  "user_id": "user123",
  "time_zone": "America/New_York",
  "working_hours": {
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"}
  },
  "preferred_meeting_times": [
    {"start": "10:00", "end": "11:00"},
    {"start": "14:00", "end": "15:00"}
  ],
  "days_off": ["saturday", "sunday"],
  "preferred_break_duration_minutes": 15,
  "work_block_max_duration_minutes": 90,
  "created_at": 1704067200000,
  "updated_at": 1704153600000
}
```

### 2. Save Preferences (POST)

**Request:**
```http
POST /preferences/{userId}
Authorization: Bearer {token}
Content-Type: application/json

{
  "user_id": "user123",
  "time_zone": "America/New_York",
  "working_hours": {
    "monday": {"start": "09:00", "end": "17:00"}
  },
  "preferred_meeting_times": [],
  "days_off": ["saturday", "sunday"],
  "preferred_break_duration_minutes": 15,
  "work_block_max_duration_minutes": 90,
  "input_mode": "both",
  "voice_button_position": "right"
}
```

**Response:** Status 200-299 indicates success

## Implementation Details

### Data Flow

#### Getting Preferences

1. **Cache Check**: First attempts to retrieve from local cache
2. **Offline Mode**: If offline and cache exists, returns cached data
3. **Authentication Check**: Verifies user has valid backend token
4. **API Request**: Fetches latest preferences from backend
5. **Cache Update**: Stores response in local cache
6. **Fallback**: Returns cached or default preferences on failure

```dart
flowchart:
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Check     │ --> │   Check     │ --> │   Make      │
│   Cache     │     │   Network   │     │   API Call  │
└─────────────┘     └─────────────┘     └─────────────┘
      │                    │                    │
      v                    v                    v
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Return    │     │   Return    │     │   Update    │
│   Cached    │     │   Cached    │     │   Cache     │
└─────────────┘     └─────────────┘     └─────────────┘
```

#### Saving Preferences

1. **Immediate Cache**: Always saves to local cache first
2. **Network Check**: Only syncs if online and authenticated
3. **Fire-and-forget**: Backend sync is non-blocking
4. **Silent Failure**: Network errors don't affect user experience

### Caching Strategy

- **Cache Key**: `"userPreferences"`
- **Storage**: Persistent local storage via CacheService
- **Update Policy**: Write-through (cache updated before API call)
- **Offline Support**: Full read/write capability offline

### Data Transformation

#### Frontend to Backend (`toBackendJson()`)
- Excludes local-only fields (`darkMode`, `created_at`, `updated_at`)
- Converts enums to string names
- Maintains nested structure for complex types

#### Backend to Frontend (`fromJson()`)
- Handles missing fields with defaults
- Parses enum strings to enum values
- Reconstructs nested objects (TimeWindow, working hours)

## Error Handling

### Network Errors
- Silent failure pattern - doesn't throw exceptions
- Falls back to cached data when available
- Returns default preferences if no cache exists

### Authentication Errors
- Missing token: Returns cached or default preferences
- Invalid token: Silent failure, uses cache

### Data Validation
- Null-safe parsing with default values
- Type checking during JSON deserialization
- Graceful handling of malformed responses

## Usage Examples

### Getting Preferences
```dart
final preferenceService = PreferenceService(
  cacheService: cacheService,
  connectivityService: connectivityService,
  authProvider: authProvider,
);

final prefs = await preferenceService.getPreferences();
print('User timezone: ${prefs.timeZone}');
print('Input mode: ${prefs.inputMode}');
```

### Updating Preferences
```dart
final updatedPrefs = currentPrefs.copyWith(
  darkMode: true,
  inputMode: InputMode.both,
  voiceButtonPosition: VoiceButtonPosition.left,
);

await preferenceService.savePreferences(updatedPrefs);
```

### Working with Time Windows
```dart
// Define working hours
final workingHours = {
  'monday': TimeWindow(start: '09:00', end: '17:00'),
  'tuesday': TimeWindow(start: '09:00', end: '17:00'),
  // ... other days
};

// Set preferred meeting times
final meetingTimes = [
  TimeWindow(start: '10:00', end: '11:00'),
  TimeWindow(start: '14:00', end: '15:00'),
];
```

## Default Values

When no preferences exist (new user or error state):
- `timeZone`: Empty string
- `workingHours`: Empty map
- `preferredMeetingTimes`: Empty list
- `daysOff`: Empty list
- `preferredBreakDurationMinutes`: 0
- `workBlockMaxDurationMinutes`: 0
- `darkMode`: false
- `inputMode`: InputMode.text
- `voiceButtonPosition`: VoiceButtonPosition.right

## Security Considerations

1. **Token Management**: Bearer tokens included in all API requests
2. **User Isolation**: Each user can only access their own preferences via userId
3. **Cache Security**: Preferences stored locally per user
4. **No Sensitive Data**: Preferences contain only UI/scheduling data

## Testing Recommendations

### Unit Tests
```dart
// Mock dependencies
final mockCache = MockCacheService();
final mockConnectivity = MockConnectivityService();
final mockAuth = MockAuthProvider();

// Test offline behavior
when(mockConnectivity.isOnline).thenReturn(false);
when(mockCache.getObject('userPreferences')).thenReturn(cachedData);

// Test sync behavior
when(mockConnectivity.isOnline).thenReturn(true);
when(mockAuth.backendAccessToken).thenReturn('valid_token');
```

### Integration Tests
- Test full sync cycle with real backend
- Verify offline/online transitions
- Test preference persistence across app restarts

## Future Enhancements

1. **Conflict Resolution**: Handle concurrent updates from multiple devices
2. **Partial Updates**: Support PATCH requests for individual preference changes
3. **Change Notifications**: Real-time updates via WebSocket/SSE
4. **Preference Versioning**: Track preference schema changes
5. **Batch Operations**: Update multiple users' preferences (admin feature)
6. **Preference Templates**: Pre-defined preference sets for common use cases

## Migration Notes

### Adding New Preferences
1. Add field to `UserPreferences` class
2. Update `fromJson()` with default value
3. Include in `toBackendJson()` if backend-synchronized
4. Update `copyWith()` method if user-editable
5. Ensure backward compatibility with existing cached data