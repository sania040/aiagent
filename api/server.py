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
NGROK_URL = "https://bbb7-2a09-bac5-503b-2723-00-3e6-40.ngrok-free.app"
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

current_call = {"sid": None, "status": None}

@app.get("/call")
def make_call():
    print("[CALL] Initiating outbound call...")
    try:
        # Use dynamic NGROK_URL instead of hardcoded URL
        ngrok_url = NGROK_URL.rstrip('/')
        call = client.calls.create(
            to=CALL_TO_NUMBER,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{ngrok_url}/voice",
            status_callback=f"{ngrok_url}/status",
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

    # Give initial greeting first
    say = ET.SubElement(response, "Say", voice="Polly.Joanna")
    say.text = "Hello, this is your AI assistant. I'm connecting you now."
    
    # Start streaming audio to our WebSocket - fix the URL format
    start = ET.SubElement(response, "Start")
    # Use the dynamic NGROK_URL variable instead of hardcoded URL
    ws_url = NGROK_URL.replace('https://', '').replace('http://', '')
    stream = ET.SubElement(start, "Stream", url=f"wss://{ws_url}/media")
    
    # Simplified approach - just start recording and let WebSocket handle everything
    say2 = ET.SubElement(response, "Say", voice="Polly.Joanna")
    say2.text = "Please speak now, I'm listening."
    
    # Keep the call open with a long pause while WebSocket processes
    pause = ET.SubElement(response, "Pause", length="300")  # 5 minutes
    
    twiml = ET.tostring(response, encoding="unicode")
    print("[WEBHOOK] Generated TwiML:", twiml)

    return Response(content=twiml, media_type="text/xml")

@app.post("/continue")
async def continue_call(_: Request):
    print("[CONTINUE] Continuing call session...")
    response = ET.Element("Response")
    
    # Just continue listening
    say = ET.SubElement(response, "Say", voice="Polly.Joanna")
    say.text = "I'm still here. Please continue speaking."
    
    # Keep the call open
    pause = ET.SubElement(response, "Pause", length="300")
    
    twiml = ET.tostring(response, encoding="unicode")
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


@app.post("/conference-status")
async def conference_status(request: Request):
    form = await request.form()
    print(f"[CONFERENCE] Status update: {dict(form)}")
    return {}


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
