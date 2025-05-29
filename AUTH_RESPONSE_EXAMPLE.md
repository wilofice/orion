# Google OAuth Connect Response Structure

## Endpoint: POST /auth/google/connect

### Request Body:
```json
{
  "authorization_code": "4/0AY0e-g7...",
  "platform": "ios",
  "code_verifier": "dBjftJeZ4CVP...",
  "redirect_uri": "com.example.app://oauth"
}
``` 

### Success Response (200 OK):
```json
{
  "message": "Successfully exchanged authorization code for Google tokens.",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user_info": {
    "email": "user@example.com",
    "google_user_id": "1234567890"
  },
  "tokens_received": {
    "access_token_present": true,
    "refresh_token_present": true,
    "id_token_present": true,
    "scopes": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/userinfo.email"
  }
}
```

### Error Responses:

#### 400 Bad Request:
```json
{
  "detail": "Invalid platform. Must be 'ios' or 'android'."
}
```

#### 503 Service Unavailable:
```json
{
  "detail": "Could not connect to Google authentication service: Connection timeout"
}
```

## Using the JWT Token:

After receiving the response, use the `access_token` in subsequent API calls:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
     https://api.example.com/auth/me
```

Response:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "user@example.com",
  "authenticated": true
}
```