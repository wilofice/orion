from calendar_api import create_event


event = {
    'summary': 'Reunion pour 01 Avril',
    'description': 'Orion testing event ',
    'start': {
        'dateTime': '2025-04-01T14:30:00+01:00',
        'timeZone': 'Europe/Paris',
    },
    'end': {
        'dateTime': '2025-04-01T16:30:00+01:00',
        'timeZone': 'Europe/Paris',
    },
    'attendees': [
    ],
}

created_event = create_event(event)
