from pydantic import BaseModel
from datetime import time, date
class Event(BaseModel):
    startTime: time
    endTime: time
    startDate: date
    endDate: date
    topic: str
    description: str
    attendees: list
    timeZone: str