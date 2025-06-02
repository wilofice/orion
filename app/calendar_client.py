# app/calendar_client.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Any, Optional

from dynamodb import refresh_google_access_token
# Assuming models.py is in the same directory or accessible via PYTHONPATH
from models import TimeSlot

from google.oauth2.credentials import Credentials as GoogleCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from scheduler_logic import filter_slots_by_preferences # Import the new function
from models import UserPreferences

# --- Configuration ---
# TODO: Move configuration details (like scopes, paths) to a config file/env vars
SCOPES = ['https://www.googleapis.com/auth/calendar'] # Start with read-only
# TODO: Replace with the actual path to your downloaded client_secret.json
CLIENT_SECRET_FILE = 'credentials/client_secret.json'
# TODO: Define path for storing user tokens after authorization
TOKEN_FILE = 'credentials/token.json'
# TODO: Define path for service account key file if using that method
SERVICE_ACCOUNT_FILE = 'credentials/service_account.json'
import asyncio


# --- Custom Exceptions ---

class CalendarAPIError(Exception):
    """Base exception for Calendar API client errors."""
    pass

class AuthenticationError(CalendarAPIError):
    """Exception raised for authentication failures."""
    pass

class APICallError(CalendarAPIError):
    """Exception raised for errors during API calls after authentication."""
    pass


# --- Abstract Base Class (for potential future providers) ---

class AbstractCalendarClient(ABC):
    """Abstract base class for calendar API clients."""

    @abstractmethod
    def authenticate(self) -> None:
        """Handles authentication with the calendar provider."""
        pass

    @abstractmethod
    def get_busy_slots(self, calendar_id: str, start_time: datetime, end_time: datetime) -> List[TimeSlot]:
        """Fetches busy time slots from the specified calendar."""
        pass

    @abstractmethod
    def calculate_free_slots(self, busy_slots: List[TimeSlot], start_time: datetime, end_time: datetime) -> List[TimeSlot]:
        """Calculates free time slots based on busy slots within a range."""
        pass

    @abstractmethod
    def get_available_time_slots(self, calendar_id: str, preferences: UserPreferences, start_time: datetime, end_time: datetime) -> List[TimeSlot]:
        """Gets available (free) time slots for a given calendar and time range."""
        pass

    @abstractmethod
    def add_event(
            self,
            title: str,
            start_time: datetime,
            end_time: datetime,
            description: Optional[str] = None,
            attendees: Optional[List[str]] = None,
            location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add an event to the calendar.

        Args:
            title: The event title/summary
            start_time: Event start datetime (timezone-aware)
            end_time: Event end datetime (timezone-aware)
            description: Optional event description/notes
            attendees: Optional list of attendee email addresses
            location: Optional location string for the event

        Returns:
            Dict containing created event details including at least:
                - id: str (The unique event ID)
                - htmlLink: str (URL to view the event)
                - status: str (Event status e.g., 'confirmed')

        Raises:
            CalendarError: If the event creation fails
        """
        pass


# --- Google Calendar API Client Implementation ---

class GoogleCalendarAPIClient(AbstractCalendarClient):
    """
    Client for interacting with the Google Calendar API using provided token information.
    """
    def __init__(self, token_info: Dict[str, Any], scopes: List[str] = SCOPES):
        """
        Initializes the Google Calendar API client using token information.

        Args:
            token_info: A dictionary containing the following keys:
                - access_token: The OAuth 2.0 access token.
                - access_token_expires_at: Expiration time of the access token.
                - scopes: List of authorized scopes.
                - google_user_id: The Google user ID.
                - refresh_token: The OAuth 2.0 refresh token.
        """
        self.token_info = token_info
        self.scopes = scopes
        self._service: Optional[Resource] = None
        self.logger = logging.getLogger(__name__)  # Setup logging

    @property
    def authenticate(self) -> None:
        """
        Authenticates the user using the provided token information and builds the service object.

        Raises:
            AuthenticationError: If authentication fails.
        """
        self.logger.info("Authenticating using provided token information...")

        try:
            # Build credentials from the access token and refresh token
            credentials = GoogleCredentials(
                token=self.token_info["access_token"],
                refresh_token=self.token_info["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=None,  # Not required for this flow
                client_secret=None,  # Not required for this flow
                scopes=self.scopes,
            )

            # Check if the token is expired and refresh if necessary
            if credentials.expired and credentials.refresh_token:
                self.logger.info("Access token expired. Attempting to refresh...")
                credentials.refresh(Request())
                self.logger.info("Access token refreshed successfully.")
            if not credentials.valid:
                new_token_data = asyncio.run(refresh_google_access_token(self.token_info["app_user_id"]))
                if new_token_data:
                    self.logger.error("Token refresh attempted successfully")
                    credentials = GoogleCredentials(
                        token=new_token_data["access_token"],
                        refresh_token=new_token_data["refresh_token"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=None,  # Not required for this flow
                        client_secret=None,  # Not required for this flow
                        scopes=self.scopes,
                    )
                    return
                else:
                    self.logger.error("Token refresh failed or no refresh token available.")
                self.logger.error("Invalid credentials. Cannot proceed.")
                raise AuthenticationError("Invalid credentials.")
            # Build the service object
            self._service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("Google Calendar API service built successfully.")

        except Exception as e:
            self.logger.error(f"Failed to authenticate and build service: {e}")
            raise AuthenticationError(f"Failed to authenticate: {e}") from e

    def _get_service(self) -> Resource:
        """
        Ensures the client is authenticated and returns the service resource.

        Returns:
            The Google Calendar API service resource.

        Raises:
            AuthenticationError: If the service is not available.
        """
        if not self._service:
            self.logger.warning("Service not available. Attempting authentication.")
            self.authenticate
            if not self._service:
                self.logger.critical("Authentication failed, service could not be built.")
                raise AuthenticationError("Cannot get service resource: Authentication failed or service not built.")
        return self._service

    # --- Service Account Authentication (Alternative) ---
    # def authenticate_service_account(self, service_account_file: str = SERVICE_ACCOUNT_FILE, scopes: List[str] = SCOPES) -> None:
    #     """Authenticates using a service account key file."""
    #     from Google.oauth2 import service_account
    #     self.logger.info("Attempting Google Calendar authentication via Service Account...")
    #     try:
    #         creds = service_account.Credentials.from_service_account_file(
    #             service_account_file, scopes=scopes)
    #         self._credentials = creds
    #         self._service = build('calendar', 'v3', credentials=self._credentials)
    #         self.logger.info("Service account authentication successful.")
    #     except FileNotFoundError:
    #         self.logger.error(f"Service account file not found: {service_account_file}")
    #         raise FileNotFoundError(f"Service account file not found: {service_account_file}")
    #     except Exception as e:
    #         self.logger.error(f"Service account authentication failed: {e}")
    #         raise AuthenticationError(f"Service account authentication failed: {e}") from e

    def _get_service(self) -> Resource:
        """Ensures the client is authenticated and returns the service resource."""
        if not self._service:
            self.logger.warning("Service not available. Attempting authentication.")
            # Decide which auth method to call by default or based on config
            self.authenticate  # Defaulting to user OAuth flow
            # self.authenticate_service_account() # Or use this if service account is the primary method
            if not self._service: # Check again after attempting auth
                 self.logger.critical("Authentication failed, service could not be built.")
                 raise AuthenticationError("Cannot get service resource: Authentication failed or service not built.")
        return self._service

    #def get_busy_slots(self, calendar_id: str = 'primary', start_time: datetime, end_time: datetime) -> List[TimeSlot]:
    def get_busy_slots(self, calendar_id: str, start_time: datetime, end_time: datetime) -> List[TimeSlot]:
        """
        Fetches busy time slots from the specified Google Calendar.

        Args:
            calendar_id: Identifier of the calendar (e.g., 'primary', email address).
            start_time: The start of the query range (timezone-aware).
            end_time: The end of the query range (timezone-aware).

        Returns:
            A list of TimeSlot objects representing busy periods.

        Raises:
            APICallError: If the API call fails.
            AuthenticationError: If authentication is required and fails.
            ValueError: If start_time or end_time are not timezone-aware.
        """
        self.logger.info(f"Fetching busy slots for calendar '{calendar_id}' from {start_time} to {end_time}")

        if start_time.tzinfo is None or end_time.tzinfo is None:
             raise ValueError("start_time and end_time must be timezone-aware.")

        service = self._get_service()
        busy_slots = []
        page_token = None

        try:
            while True:
                # Convert to ISO format string required by API
                time_min = start_time.isoformat()
                time_max = end_time.isoformat()

                self.logger.debug(f"Calling events.list: calendarId={calendar_id}, timeMin={time_min}, timeMax={time_max}, pageToken={page_token}")

                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True, # Expand recurring events
                    orderBy='startTime',
                    pageToken=page_token,
                    # Consider adding maxResults if needed
                ).execute()

                events = events_result.get('items', [])
                self.logger.debug(f"Received {len(events)} events in this page.")

                for event in events:
                    # Skip events user declined or didn't respond to? Optional.
                    # user_status = None
                    # if 'attendees' in event:
                    #     for attendee in event['attendees']:
                    #         if attendee.get('self'):
                    #             user_status = attendee.get('responseStatus')
                    #             break
                    # if user_status in ['declined', 'needsAction', 'tentative']:
                    #      self.logger.debug(f"Skipping event '{event.get('summary', 'N/A')}' due to status: {user_status}")
                    #      continue

                    # Skip transparent events (marked as "Free")
                    if event.get('transparency') == 'transparent':
                        self.logger.debug(f"Skipping transparent event: {event.get('summary', 'N/A')}")
                        continue

                    # Extract start and end times
                    start_str = event['start'].get('dateTime', event['start'].get('date'))
                    end_str = event['end'].get('dateTime', event['end'].get('date'))

                    # Handle all-day events vs timed events
                    # All-day events have 'date' field, timed events have 'dateTime'
                    if 'dateTime' in event['start']:
                        # Timed event, parse with timezone
                        event_start = datetime.fromisoformat(start_str)
                        event_end = datetime.fromisoformat(end_str)
                    else:
                        # All-day event. API returns date string 'YYYY-MM-DD'.
                        # Represents the entire day in the calendar's timezone.
                        # We need to convert this to a timezone-aware start/end datetime
                        # spanning the whole day in the *user's* target timezone for consistency.
                        # This requires knowing the calendar's timezone, which adds complexity.
                        # Simpler approach: treat all-day events as blocking the entire day
                        # in the query timezone IF the date falls within the query range.
                        # More robust: Fetch calendar timezone, convert properly.
                        # For now, let's use a simplified approach assuming UTC or the query timezone.
                        # WARNING: This simplification might be inaccurate for users across timezones.
                        try:
                            event_date = date.fromisoformat(start_str)
                            # Assume the all-day event blocks the entire day in the query's start_time timezone
                            tz = start_time.tzinfo
                            event_start = datetime.combine(event_date, time.min, tzinfo=tz)
                            # End date from API is exclusive, so use the next day's start
                            event_end_date = date.fromisoformat(end_str)
                            event_end = datetime.combine(event_end_date, time.min, tzinfo=tz)

                            # Clamp to query range to avoid huge slots from long all-day events
                            event_start = max(event_start, start_time)
                            event_end = min(event_end, end_time)

                            # If the resulting slot is invalid (end <= start), skip it
                            if event_end <= event_start:
                                self.logger.debug(f"Skipping all-day event '{event.get('summary', 'N/A')}' as it falls outside clamped range.")
                                continue

                        except ValueError as e:
                            self.logger.warning(f"Could not parse all-day event dates for '{event.get('summary', 'N/A')}': {start_str}, {end_str}. Error: {e}. Skipping.")
                            continue

                    # Create TimeSlot only if it's valid
                    if event_end > event_start:
                         # Clamp event times to the query window to avoid including time outside the requested range
                        clamped_start = max(event_start, start_time)
                        clamped_end = min(event_end, end_time)

                        # Only add if there's an actual overlap within the query window
                        if clamped_end > clamped_start:
                            busy_slots.append(TimeSlot(start_time=clamped_start, end_time=clamped_end))
                            self.logger.debug(f"Added busy slot: {clamped_start} - {clamped_end} from event '{event.get('summary', 'N/A')}'")
                        else:
                            self.logger.debug(f"Event '{event.get('summary', 'N/A')}' ({event_start} - {event_end}) falls outside query window after clamping.")

                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break # Exit loop if no more pages

            # Sort slots just in case API doesn't guarantee strict order with pagination/expansion
            busy_slots.sort(key=lambda slot: slot.start_time)
            self.logger.info(f"Successfully fetched {len(busy_slots)} busy slots.")
            return busy_slots

        except HttpError as error:
            self.logger.error(f"An API error occurred: {error}")
            # TODO: Add more specific error handling (e.g., 401/403 for auth, 404 for calendar not found, rate limits)
            if error.resp.status in [401, 403]:
                 raise AuthenticationError(f"API authentication/authorization error: {error}") from error
            else:
                 raise APICallError(f"API call failed: {error}") from error
        except Exception as e:
            # Catch other potential errors (network, parsing, etc.)
            self.logger.exception(f"An unexpected error occurred during get_busy_slots: {e}")
            raise APICallError(f"An unexpected error occurred: {e}") from e


    def calculate_free_slots(self, busy_slots: List[TimeSlot], start_time: datetime, end_time: datetime) -> List[TimeSlot]:
        """
        Calculates free time slots based on a sorted list of busy slots.

        Args:
            busy_slots: A sorted list of non-overlapping TimeSlot objects representing busy periods.
            start_time: The overall start time of the period to consider (timezone-aware).
            end_time: The overall end time of the period to consider (timezone-aware).

        Returns:
            A list of TimeSlot objects representing free periods.

        Raises:
            ValueError: If start_time or end_time are not timezone-aware or end_time <= start_time.
        """
        self.logger.info(f"Calculating free slots between {start_time} and {end_time}")
        if start_time.tzinfo is None or end_time.tzinfo is None:
             raise ValueError("start_time and end_time must be timezone-aware.")
        if end_time <= start_time:
             raise ValueError("end_time must be after start_time for calculation.")

        free_slots = []
        current_free_start = start_time

        # Merge overlapping/adjacent busy slots first (optional but recommended for robustness)
        # If get_busy_slots guarantees non-overlapping, this can be skipped.
        # merged_busy = self._merge_overlapping_slots(busy_slots) # Implement this helper if needed

        for busy_slot in busy_slots: # Use merged_busy if implemented
            # Ensure busy slot is within the overall range
            if busy_slot.end_time <= current_free_start:
                continue # This busy slot is entirely before our current free start point
            if busy_slot.start_time >= end_time:
                break # This busy slot (and all subsequent ones) are after our overall end time

            # Clamp busy slot to the query range
            effective_busy_start = max(busy_slot.start_time, start_time)
            effective_busy_end = min(busy_slot.end_time, end_time)

            # If there's a gap between the current free start and the busy slot start
            if effective_busy_start > current_free_start:
                free_slots.append(TimeSlot(start_time=current_free_start, end_time=effective_busy_start))
                self.logger.debug(f"Found free slot: {current_free_start} - {effective_busy_start}")

            # Move the current free start pointer to the end of this busy slot
            current_free_start = max(current_free_start, effective_busy_end)

        # If there's remaining free time after the last busy slot
        if current_free_start < end_time:
            free_slots.append(TimeSlot(start_time=current_free_start, end_time=end_time))
            self.logger.debug(f"Found final free slot: {current_free_start} - {end_time}")

        self.logger.info(f"Calculated {len(free_slots)} free slots.")
        return free_slots

    # --- Helper for merging overlaps (Optional) ---
    # def _merge_overlapping_slots(self, slots: List[TimeSlot]) -> List[TimeSlot]:
    #     if not slots:
    #         return []
    #     # Ensure slots are sorted by start time
    #     slots.sort(key=lambda s: s.start_time)
    #     merged = [slots[0]]
    #     for current in slots[1:]:
    #         last = merged[-1]
    #         if current.start_time < last.end_time: # Overlap or adjacent
    #             # Merge: extend the end time of the last slot
    #             merged[-1] = TimeSlot(start_time=last.start_time,
    #                                     end_time=max(last.end_time, current.end_time))
    #         else:
    #             merged.append(current)
    #     return merged

    def get_available_time_slots(
            self,
            preferences: UserPreferences,  # Add UserPreferences as input
            calendar_id: str,
            start_time: datetime,
            end_time: datetime
    ) -> List[TimeSlot]:
        """
        Gets available (free) time slots considering both calendar events
        and user preferences.

        Args:
            preferences: The UserPreferences object for the user.
            calendar_id: Identifier of the calendar.
            start_time: The start of the query range (timezone-aware).
            end_time: The end of the query range (timezone-aware).

        Returns:
            A list of TimeSlot objects representing available periods.

        Raises:
            APICallError, AuthenticationError, ValueError as per underlying methods.
        """
        self.logger.info(f"Getting available time slots for calendar '{calendar_id}' considering preferences.")

        # Step 1: Get busy slots from the calendar API
        calendar_busy_slots = self.get_busy_slots(calendar_id, start_time, end_time)

        # Step 2: Calculate the raw free slots based on calendar busy times
        # (Uses the calculate_free_slots method already defined in this class)
        raw_free_slots = self.calculate_free_slots(calendar_busy_slots, start_time, end_time)

        # Step 3: Filter the raw free slots using user preferences
        filtered_free_slots = filter_slots_by_preferences(raw_free_slots, preferences)

        self.logger.info(f"Calculated {len(filtered_free_slots)} final available slots after applying preferences.")
        return filtered_free_slots

    def add_event(
            self,
            title: str,
            start_time: datetime,
            end_time: datetime,
            description: Optional[str] = None,
            attendees: Optional[List[str]] = None,
            location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add an event to the calendar.

        Args:
            title: The event title/summary
            start_time: Event start datetime (timezone-aware)
            end_time: Event end datetime (timezone-aware)
            description: Optional event description/notes
            attendees: Optional list of attendee email addresses
            location: Optional location string for the event

        Returns:
            Dict containing created event details including at least:
                - id: str (The unique event ID)
                - htmlLink: str (URL to view the event)
                - status: str (Event status e.g., 'confirmed')

        Raises:
            CalendarError: If the event creation fails
        """
        try:
            service = self._get_service()

            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_time.isoformat(),
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                },
                'attendees': [],
            }
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            return created_event
        except Exception as e:
            # Log the error or handle it appropriately
            print(f"An error occurred while creating the event: {e}")
            return None



