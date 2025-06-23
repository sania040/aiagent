from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import requests
from pydantic import BaseModel
import openai
import os
from tempfile import NamedTemporaryFile
import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Enable CORS for your React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure OpenAI - replace with your actual API key
openai.api_key = os.getenv("OPENAI_API_KEYs")

# Constants for Simli API
SIMLI_SESSION_ID = os.getenv("SIMLI_SESSION_ID")
SIMLI_TOKEN = os.getenv("SIMLI_TOKEN")
SIMLI_ROOM_URL = os.getenv("SIMLI_ROOM_URL", "https://pc-7efd6f2a87c8db0e8fe4ea108a6e11b6.daily.co/hoHfCDtVcKbk3uy8l2LB")
SIMLI_API_URL = os.getenv("SIMLI_API_URL", "http://localhost:8000/api/avatar-speak")

# Define request models
class TextToSpeech(BaseModel):
    text: str
    voice_id: str = "default"

class TextRequest(BaseModel):
    text: str

@app.get("/api/room-url")
async def get_room_url():
    """
    Python function to fetch the room URL from Simli API
    """
    try:
        url = f"https://api.simli.ai/session/{SIMLI_SESSION_ID}/{SIMLI_TOKEN}"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API request failed with status: {response.status_code}")
            
        data = response.json()
        return {"roomUrl": data.get("roomUrl")}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
