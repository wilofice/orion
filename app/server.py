from fastapi import FastAPI
from .models import Event
from .calendar_api import schedule_event
app = FastAPI()

@app.post("/events")
async def post_event(event: Event):

    created_event = schedule_event(event.startDate, event.startTime, event.endDate, event.endTime, event.topic, event.description, event.timeZone)

    return dict(
        status="success",
        message="Event created successfully",
        event=created_event
    )
