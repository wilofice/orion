# Audio URL Implementation for Voice Messages

## Overview

This document describes the implementation of audio URL support in the Orion API, enabling the handling of voice messages as part of the chat functionality. The implementation allows the Flutter-based frontend to send audio URLs (stored in S3) along with transcribed text to the backend API.

## Implementation Details

### 1. Model Updates

#### ChatRequest Model
Added optional `audio_url` field to support voice messages:
```python
audio_url: Optional[str] = Field(None, description="Optional URL of the audio file stored in S3 for voice messages.")
```

#### ConversationTurn Model
Updated to support audio messages in conversation history:
- Added `AudioMessage` class for structured audio data
- Updated `ContentData` union type to include audio messages
- Modified `user_turn` class method to accept optional audio URL

### 2. API Endpoint Updates

#### /chat/prompt Endpoint
- Now accepts `audio_url` in the request body
- Passes audio URL through to the orchestration service
- Maintains backward compatibility (audio_url is optional)

#### /conversations/{user_id} Endpoint
- Updated to handle both text and audio message formats
- Returns audio URLs along with transcripts in conversation history
- Properly filters and formats messages for frontend consumption

### 3. Data Flow

1. **Client sends audio message**:
   - Records audio locally
   - Transcribes using speech-to-text
   - Uploads audio to S3
   - Sends both transcript and S3 URL to `/chat/prompt`

2. **Backend processes request**:
   - Receives ChatRequest with audio_url
   - Creates ConversationTurn with audio data
   - Stores in DynamoDB (audio URL preserved)
   - AI processes the transcript text

3. **Client retrieves history**:
   - Calls `/conversations/{user_id}`
   - Receives messages with audio URLs intact
   - Can playback audio from S3 URLs

## Testing Recommendations

### Unit Tests

1. **Model Validation Tests**
   - Test ChatRequest with valid audio URLs
   - Test ChatRequest without audio URLs (backward compatibility)
   - Test invalid URL formats
   - Test ConversationTurn creation with audio data

2. **Endpoint Tests**
   - Test `/chat/prompt` with audio URLs
   - Test `/chat/prompt` without audio URLs
   - Test `/conversations/{user_id}` returns audio URLs correctly
   - Test filtering of conversation roles

3. **Integration Tests**
   - Test full flow: audio URL → storage → retrieval
   - Test session management with mixed text/audio messages
   - Test error handling for inaccessible audio URLs

### Performance Tests

1. **Latency Testing**
   - Measure additional latency from audio URL handling
   - Test concurrent audio message processing
   - Benchmark conversation retrieval with audio messages

2. **Load Testing**
   - Test system under high volume of audio messages
   - Test S3 URL validation under load
   - Test DynamoDB performance with audio data

### Security Tests

1. **URL Validation**
   - Test SSRF prevention
   - Validate only allowed S3 buckets
   - Test URL injection attempts

2. **Access Control**
   - Verify users can only access their own audio URLs
   - Test cross-user audio URL access attempts
   - Validate S3 bucket permissions

## Future Enhancements

### 1. Audio Processing Pipeline
- **Real-time transcription**: Stream audio for live transcription
- **Audio analytics**: Extract metadata (duration, quality, language)
- **Compression**: Optimize audio storage and bandwidth
- **Multiple formats**: Support various audio codecs

### 2. Enhanced AI Integration
- **Audio context**: Pass audio characteristics to AI (tone, emotion)
- **Multi-modal responses**: AI generates audio responses
- **Language detection**: Auto-detect spoken language
- **Speaker identification**: Multi-user conversation support

### 3. Storage Optimization
- **CDN integration**: Distribute audio files globally
- **Lifecycle policies**: Auto-archive old audio files
- **Presigned URL caching**: Reduce S3 API calls
- **Progressive loading**: Stream large audio files

### 4. Advanced Features
- **Audio search**: Search conversations by audio content
- **Transcript correction**: Allow users to edit transcriptions
- **Audio summarization**: Generate summaries of long audio
- **Offline support**: Queue audio for later processing

### 5. Monitoring and Analytics
- **Audio quality metrics**: Track transcription accuracy
- **Usage analytics**: Monitor audio vs text message ratios
- **Performance dashboards**: Real-time audio processing metrics
- **Error tracking**: Monitor failed audio processing

### 6. Accessibility
- **Alternative formats**: Generate text summaries for audio
- **Playback controls**: Speed adjustment, skip silence
- **Visual indicators**: Waveform visualization
- **Subtitle generation**: Real-time captions

## Security Considerations

1. **S3 Access**
   - Use presigned URLs with expiration
   - Implement bucket policies for user isolation
   - Enable S3 access logging

2. **Content Validation**
   - Scan audio files for malware
   - Validate audio file formats
   - Implement size limits

3. **Privacy**
   - Encrypt audio files at rest
   - Implement retention policies
   - Provide user controls for deletion

## Deployment Checklist

- [ ] Update API documentation with audio_url field
- [ ] Configure S3 bucket policies
- [ ] Set up CloudFront for audio delivery
- [ ] Implement monitoring for audio processing
- [ ] Update client SDKs with audio support
- [ ] Train support team on audio features
- [ ] Create user documentation

## Conclusion

The audio URL implementation provides a foundation for voice message support while maintaining backward compatibility. The architecture is designed to be extensible, allowing for future enhancements in audio processing and AI integration.