from pydantic import BaseModel
from typing import Optional, List

class Event(BaseModel):
    summary: str
    description: Optional[str] = None
    start: dict
    end: dict
    attendees: Optional[List[dict]] = None
    # Ajoutez d'autres champs pertinents