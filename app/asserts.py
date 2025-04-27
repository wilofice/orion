import unittest
import unittest
from unittest.mock import patch
from datetime import datetime
from jobs import get_available_time_slots

class MyTestCase(unittest.TestCase):
    def test_something(self):
        self.assertEqual(True, True)  # add assertion here


class TestGetAvailableTimeSlots(unittest.TestCase):
    @patch('jobs.get_filtered_events')
    def test_no_planned_events(self, mock_get_filtered_events):
        # Mock no planned events
        mock_get_filtered_events.return_value = []

        startDate = "2023-10-01"
        startTime = "09:00:00"
        endDate = "2023-10-01"
        endTime = "10:00:00"

        # Call the method
        result = get_available_time_slots(startDate, startTime, endDate, endTime)

        # Expected 20-minute slots
        expected = [
            {"start": "2023-10-01 09:00:00", "end": "2023-10-01 09:20:00"},
            {"start": "2023-10-01 09:20:00", "end": "2023-10-01 09:40:00"},
            {"start": "2023-10-01 09:40:00", "end": "2023-10-01 10:00:00"},
        ]

        self.assertEqual(result, expected)

    @patch('jobs.get_filtered_events')
    def test_with_overlapping_events(self, mock_get_filtered_events):
        # Mock overlapping events
        mock_get_filtered_events.return_value = [
            {"startDate": "2023-10-01", "startTime": "09:10:00", "endDate": "2023-10-01", "endTime": "09:30:00", "topic": "Meeting", "description": "Team meeting", "attendees": []},
        ]

        startDate = "2023-10-01"
        startTime = "09:00:00"
        endDate = "2023-10-01"
        endTime = "10:00:00"

        # Call the method
        result = get_available_time_slots(startDate, startTime, endDate, endTime)

        # Expected 20-minute slots excluding the overlapping one
        expected = [
            {"start": "2023-10-01 09:00:00", "end": "2023-10-01 09:10:00"},
            {"start": "2023-10-01 09:30:00", "end": "2023-10-01 09:50:00"},
            {"start": "2023-10-01 09:50:00", "end": "2023-10-01 10:00:00"},
        ]

        self.assertEqual(result, expected)

    @patch('jobs.get_filtered_events')
    def test_with_non_overlapping_events(self, mock_get_filtered_events):
        # Mock non-overlapping events
        mock_get_filtered_events.return_value = [
            {"startDate": "2023-10-01", "startTime": "08:00:00", "endDate": "2023-10-01", "endTime": "08:30:00", "topic": "Meeting", "description": "Team meeting", "attendees": []},
        ]

        startDate = "2023-10-01"
        startTime = "09:00:00"
        endDate = "2023-10-01"
        endTime = "10:00:00"

        # Call the method
        result = get_available_time_slots(startDate, startTime, endDate, endTime)

        # Expected 20-minute slots (no overlap)
        expected = [
            {"start": "2023-10-01 09:00:00", "end": "2023-10-01 09:20:00"},
            {"start": "2023-10-01 09:20:00", "end": "2023-10-01 09:40:00"},
            {"start": "2023-10-01 09:40:00", "end": "2023-10-01 10:00:00"},
        ]

        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()

