import os
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request
from handlers.twilio_pipeline_handler import handle_twilio_websocket
import logging

# Load environment variables (redundant if loaded in main.py, but safe)
load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "AI Agent is running"}

@app.websocket("/media")
async def media_ws(websocket: WebSocket):
    logger.info("Received incoming WebSocket connection on /media")
    await handle_twilio_websocket(websocket)

# Optional: Add a webhook endpoint for Twilio status updates if needed
# @app.post("/status")
async def handle_status_update(request: Request):
    form_data = await request.form()
    logger.info(f"Twilio Status Update: {form_data}")
    return {"status": "received"}
