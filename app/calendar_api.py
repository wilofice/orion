from googleapiclient.discovery import  build
from google.oauth2 import service_account

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
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