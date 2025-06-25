# api/server.py
import os
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import PlainTextResponse
from twilio.rest import Client
import xml.etree.ElementTree as ET
from handlers.twilio_pipeline_handler import handle_twilio_websocket
import time
from fastapi.responses import Response
load_dotenv()

app = FastAPI()

# twilio setup
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
CALL_TO_NUMBER = os.getenv("CALL_TO_NUMBER")  # set in .env
NGROK_URL = os.getenv("NGROK_URL")  # set in .env
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

current_call = {"sid": None, "status": None}

@app.get("/call")
def make_call():
    print("[CALL] Initiating outbound call...")
    try:
        call = client.calls.create(
            to=CALL_TO_NUMBER,
            from_=TWILIO_PHONE_NUMBER,
            url=f"https://9ce0-2a09-bac1-5b20-48-00-3c4-45.ngrok-free.app/voice",
            status_callback=f"https://9ce0-2a09-bac1-5b20-48-00-3c4-45.ngrok-free.app/status",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )
        print(f"[CALL] Call initiated. SID: {call.sid}")
        current_call.update({"sid": call.sid, "status": "initiated"})
        return {"status": "initiated", "sid": call.sid}
    except Exception as e:
        return {"error": str(e)}



@app.post("/voice")
async def voice_webhook(_: Request):
    print("[WEBHOOK] Twilio voice webhook hit.")
    response = ET.Element("Response")

    start = ET.SubElement(response, "Start")
    ET.SubElement(start, "Stream", url=f"wss://{NGROK_URL}/media")

    say = ET.SubElement(response, "Say")
    say.text = "Hello, this is your legal AI assistant. How can I help you today?"

    gather = ET.SubElement(response, "Gather", input="speech", timeout="20", action="/fallback", method="POST")
    gather.text = ""

    twiml = ET.tostring(response, encoding="unicode")
    print("[WEBHOOK] Generated TwiML:", twiml)

    return Response(content=twiml, media_type="text/xml")


@app.post("/fallback")
async def fallback(_: Request):
    print("[FALLBACK] No speech detected. Sending polite message.")
    response = ET.Element("Response")
    say = ET.SubElement(response, "Say")
    say.text = "Sorry, I didn't hear anything. Please call again when you're ready."
    hangup = ET.SubElement(response, "Hangup")
    twiml = ET.tostring(response, encoding="unicode")
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/media")
async def media_ws(websocket: WebSocket):
    print("[WEBSOCKET] Incoming Twilio stream connection...")
    await handle_twilio_websocket(websocket)

@app.post("/status")
async def call_status(request: Request):
    form = await request.form()
    status = form.get("CallStatus")
    sid = form.get("CallSid")
    # Modify the print statement to show only status and sid
    print(f"[CALL STATUS] SID: {sid}, Status: {status}")
    if sid == current_call["sid"]:
        current_call["status"] = status
        if status in {"busy", "failed", "no-answer"}:
             print(f"Call {current_call['status']} ended. Retry or cleanup.")

    return {"status": status, "sid": sid}


def retry_call():
    retries = 3
    while retries > 0:
        call_status = make_call()
        if call_status.get("status") == 'busy':
            print("Call busy, retrying...")
            retries -= 1
            time.sleep(10)  # Wait before retrying
        elif call_status == 'completed':
            print("Call completed successfully.")
            break
        else:
            retries -= 1

    return ""
@app.get("/status")
def get_status():
    return current_call
