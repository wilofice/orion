from fastapi import FastAPI, Depends
from .models import Event
from .quick_init_calendar_service import create_event, schedule_event
from .database import insert_document
from bson import ObjectId


app = FastAPI()

@app.post("/events/")
async def post_event(event: Event):
    # We'll add the logic here to interact with Google Calendar
    created_event = schedule_event(event.startDate, event.startTime, event.endDate, event.endTime, event.topic, event.description, "Europe/Paris")

    insert_document("events", created_event)
    created_event.pop('_id', None)
    return dict(message="Event creation request received", event_details=created_event)