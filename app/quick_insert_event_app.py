from fastapi import FastAPI, Depends
from .models import Event
from .quick_init_calendar_service import create_event, schedule_event
# MongoDB storage removed. Events are scheduled directly.


app = FastAPI()

@app.post("/events/")
async def post_event(event: Event):
    # We'll add the logic here to interact with Google Calendar
    created_event = schedule_event(event.startDate, event.startTime, event.endDate, event.endTime, event.topic, event.description, "Europe/Paris")

    created_event.pop('_id', None)
    return dict(message="Event creation request received", event_details=created_event)