from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os.path

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('calendar', 'v3', credentials=creds)
    return service

def get_events():
    service = get_calendar_service()
    events = service.events().list(calendarId='primary').execute()
    return events

def create_event(event):
    service = get_calendar_service()
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return created_event


def schedule_event(startDate, startTime, endDate, endTime, topic, description, timeZone):
    event = {
        'summary': topic,
        'description': description,
        'start': {
            'dateTime': f'{startDate}T{startTime}',
            'timeZone': timeZone,
        },
        'end': {
            'dateTime': f'{endDate}T{endTime}',
            'timeZone': timeZone,
        },
        'attendees': [],
    }

    return create_event(event)
