from fastapi import FastAPI, HTTPException
from .models import Event
from .database import db
from .calendar_api import get_calendar_service, create_event

app = FastAPI()

@app.post("/events/", response_model=Event)
async def create_event_endpoint(event: Event):
    # Logique pour créer un événement dans MongoDB et Google Calendar
    service = get_calendar_service()
    google_event = create_event(event.dict())
    event_id = db.events.insert_one(event.dict()).inserted_id
    return {**event.dict(), "id": str(event_id)}

# Ajoutez d'autres endpoints pour lire, mettre à jour et supprimer des événements