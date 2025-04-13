from fastapi import FastAPI, Depends
from .models import Event
from .calendar_api import create_event, schedule_event

app = FastAPI()

@app.post("/events/")
async def post_event(event: Event):
    # We'll add the logic here to interact with Google Calendar
    created_event = schedule_event(event.startDate, event.startTime, event.endDate, event.endTime, event.topic, event.description, "Europe/Paris")

    return dict(message="Event creation request received", event_details=created_event)