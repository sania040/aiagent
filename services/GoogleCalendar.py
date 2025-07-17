import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import logging
import json

logger = logging.getLogger(__name__)

class GoogleCalendarService:
    def __init__(self):
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            logger.error(f"Google Service Account file not found: {SERVICE_ACCOUNT_FILE}")
            self.service = None
            return
        if not self.calendar_id:
            logger.error("GOOGLE_CALENDAR_ID not found in environment variables.")
            self.service = None
            return

        try:
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("Google Calendar service initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Google Calendar service: {e}")
            self.service = None


    def create_appointment(self, summary, description, start_time, end_time, attendees):
        """
        Creates an event on the Google Calendar.
        start_time and end_time should be in RFC3339 format (e.g., '2025-07-02T10:00:00-05:00' or '2025-07-02T10:00:00').
        """
        if not self.service:
            logger.error("Google Calendar service is not initialized.")
            return None

        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': 'America/New_York'}, # Use your desired timezone
            'end': {'dateTime': end_time, 'timeZone': 'America/New_York'},     # Use your desired timezone
            'attendees': [{'email': email} for email in attendees if email],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60}, # 24 hours before
                    {'method': 'popup', 'minutes': 10},      # 10 minutes before
                ],
            },
        }

        logger.info(f"Attempting to create calendar event: {event}")

        try:
            event = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
            logger.info(f"Event created: {event.get('htmlLink')}")
            return event.get('htmlLink')
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return None

    # This method was called in langchain_agent.py but not defined.
    # You need to implement logic here to parse the 'info' string/dict
    # from the LangChain agent and call create_appointment.
    def create_appointment_from_string(self, info_str: str):
        """
        Parses a string (presumably from LangChain agent) to extract appointment details
        and calls create_appointment.
        You need to implement the parsing logic based on your agent's output format.
        """
        logger.warning(f"create_appointment_from_string called with: {info_str}. Parsing logic needs implementation.")
        # Example parsing (assuming info_str is a JSON string)
        try:
            info = json.loads(info_str) # Assuming agent outputs JSON
            summary = f"Viewing with {info.get('name', 'Lead')}"
            description = f"Phone: {info.get('phone', 'N/A')}\nAddress: {info.get('address', 'N/A')}"
            # Need robust date/time parsing here
            start_time_str = info.get('date') + 'T' + info.get('time') + ':00' # Example format
            # Calculate end time (e.g., +30 mins)
            from datetime import datetime, timedelta
            try:
                start_dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
                end_dt = start_dt + timedelta(minutes=30)
                end_time_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                 logger.error(f"Failed to parse date/time string: {start_time_str}")
                 return None # Cannot book without valid time

            attendees = [info.get('email')]

            return self.create_appointment(summary, description, start_time_str, end_time_str, attendees)

        except json.JSONDecodeError:
            logger.error(f"Failed to parse info string as JSON: {info_str}")
            return None
        except Exception as e:
            logger.error(f"Error in create_appointment_from_string: {e}")
            return None