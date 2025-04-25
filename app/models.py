from datetime import date, datetime, time, timedelta
from pydantic import BaseModel

class Event(BaseModel):
    startTime: time
    endTime: time
    endDate: date
    startDate: date
    topic: str
    description: str
    attendees: list[str]


# print(
#     Event(
#         name='Apple',
#     )
# )
