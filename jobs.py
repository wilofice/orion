import threading
import time
from app.database import get_all_documents, get_filtered_events
from app.models import Event
from pydantic import ValidationError
import json

def background_task():
    while True:
        print(f"Background task running at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        # Perform your background work here
        time.sleep(5)  # Run every 5 seconds


def get_events(startDate, startTime, endDate, endTime):
    # Retrieve all documents from the "events" collection
    events = get_filtered_events("events", startDate, startTime, endDate, endTime)
    event_objects = []

    for event in events:
        try:
            # Map each document to the Event model
            event_obj = Event(**event)
            event_objects.append(event_obj)
            print(f"Event: {event_obj.topic} at {event_obj.startDate}")
        except ValidationError as e:
            print(f"Validation error for event: {event}. Error: {e}")

    return event_objects

def get_events_as_json(startDate, startTime, endDate, endTime):
    # Retrieve filtered events from the database
    events = get_filtered_events("events", startDate, startTime, endDate, endTime)
    event_objects = []

    for event in events:
        try:
            # Map each document to the Event model
            event_obj = Event(**event)
            event_objects.append(event_obj.dict())  # Convert to dictionary
        except ValidationError as e:
            print(f"Validation error for event: {event}. Error: {e}")

    # Return the list of events as JSON
    return json.dumps(event_objects)



from datetime import datetime, timedelta

def get_available_time_slots(startDate, startTime, endDate, endTime):
    """
    Returns available 20-minute time slots within the given date and time range.
    """
    # Parse input parameters into datetime objects
    start_datetime = datetime.strptime(f"{startDate} {startTime}", "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.strptime(f"{endDate} {endTime}", "%Y-%m-%d %H:%M:%S")

    # Retrieve planned events
    events = get_filtered_events("events", startDate, startTime, endDate, endTime)
    planned_slots = []

    for event in events:
        try:
            # Map each document to the Event model
            event_obj = Event(**event)
            event_start = datetime.strptime(f"{event_obj.startDate} {event_obj.startTime}", "%Y-%m-%d %H:%M:%S")
            event_end = datetime.strptime(f"{event_obj.endDate} {event_obj.endTime}", "%Y-%m-%d %H:%M:%S")
            planned_slots.append((event_start, event_end))
        except ValidationError as e:
            print(f"Validation error for event: {event}. Error: {e}")

    # Sort planned_slots by event_start (first element of each tuple)
    planned_slots.sort(key=lambda x: x[0])

    # Generate all 20-minute slots within the range
    available_slots = []
    current_slot = start_datetime
    while current_slot < end_datetime:
        next_slot = current_slot + timedelta(minutes=20)
        if next_slot > end_datetime:
            next_slot = end_datetime
        # Check if the slot overlaps with any planned event
        slot_is_available = True
        for event_start, event_end in planned_slots:
            # An overlap occurs if the event either starts during the slot
            # or ends during the slot, or completely encompasses the slot
            if (current_slot <= event_start < next_slot) or \
               (current_slot < event_end <= next_slot) or \
               (event_start <= current_slot and event_end >= next_slot):
                slot_is_available = False
                # Move the current slot to the end of the overlapping event
                current_slot = max(current_slot, event_end)
                break
        if slot_is_available:
            available_slots.append((current_slot, next_slot))
            current_slot = next_slot
        else:
            current_slot = min(current_slot, end_datetime)

    # Format the available slots as strings
    return [
        {"start": slot[0].strftime("%Y-%m-%d %H:%M:%S"), "end": slot[1].strftime("%Y-%m-%d %H:%M:%S")}
        for slot in available_slots
    ]

if __name__ == "__main__":
    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    print("Main program continues to run...")
    # Your main program logic here
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Main program interrupted. Background task will exit.")