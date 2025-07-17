import os
import time
import json
import logging
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables
load_dotenv()

# Twilio credentials and numbers from .env
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
TO_NUMBER = os.getenv("CALL_TO_NUMBER") # Ensure this matches your .env
AGENT_MEDIA_URL = os.getenv("AGENT_MEDIA_URL", "wss://your-server.com/media")

# Set up logging (ensure this doesn't duplicate handlers if main.py sets it up)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     handlers=[logging.StreamHandler()]
# )
logger = logging.getLogger(__name__)

def make_call():
    logger.info("Starting outbound call...")

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.error("Twilio credentials not found in environment variables.")
        return
    if not FROM_NUMBER:
        logger.error("Twilio FROM_NUMBER not found in environment variables.")
        return
    if not TO_NUMBER:
        logger.error("LEAD_PHONE_NUMBER (CALL_TO_NUMBER) not found in environment variables.")
        return
    if not AGENT_MEDIA_URL or "your-server.com" in AGENT_MEDIA_URL:
         logger.warning(f"AGENT_MEDIA_URL is not set or is default: {AGENT_MEDIA_URL}. Ensure ngrok/public URL is correct.")


    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    # TwiML: Start stream, play greeting, keep call open for 5 minutes
    # Removed <Say> here to let the handler control the greeting
    twiml = f"""
        <Response>
            <Start>
                <Stream url="{AGENT_MEDIA_URL}" />
            </Start>
            <Pause length="300"/>
        </Response>
    """

    payload = {
        "to": TO_NUMBER,
        "from_": FROM_NUMBER,
        "twiml": twiml,
        "record": True # Add this line to enable recording
    }

    logger.info("Payload to Twilio:")
    print(json.dumps(payload, indent=2))

    try:
        call = client.calls.create(**payload)
        logger.info("Twilio response attributes:")
        # Use __dict__ to get attributes, handle non-serializable types
        print(json.dumps(call.__dict__, indent=2, default=str))
        logger.info(f"Call initiated. SID: {call.sid}")
        logger.info(f"Call status: {call.status}")

        # Poll for call status updates (optional, but good for monitoring)
        logger.info("Polling for call status updates...")
        # Poll for a reasonable time, e.g., 60 seconds (12 * 5s)
        for _ in range(12):
            try:
                call = client.calls(call.sid).fetch()
                logger.info(f"Call status: {call.status}")
                if call.status in ["completed", "canceled", "failed", "busy", "no-answer"]:
                    logger.info(f"Call ended with status: {call.status}")
                    break
            except Exception as fetch_error:
                 logger.error(f"Error fetching call status for SID {call.sid}: {fetch_error}")
                 break # Stop polling if fetch fails
            time.sleep(5)
        else:
            logger.info("Stopped polling after 60 seconds.")

        logger.info("Waiting for call to connect and stream media to /media endpoint...")
        logger.info("Check your FastAPI/ngrok logs for incoming media stream events.")

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")

if __name__ == "__main__":
    make_call()