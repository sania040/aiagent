import os
import openai
from dotenv import load_dotenv
import tempfile
import pygame

class TextToSpeech:
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv("OPENAI_API_KEY")
        pygame.init()
        pygame.mixer.init()

    def generate_speech(self, text, voice="alloy"):
        try:
            # Call OpenAI TTS API
            response = openai.audio.speech.create(
                model="tts-1",
                voice=voice,  # Options: 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'
                input=text
            )
            # Save to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                fp.write(response.content)
                temp_path = fp.name
            return temp_path
        except Exception as e:
            print(f"Error generating speech: {e}")
            return None

    def play_audio(self, file_path):
        try:
            if file_path and os.path.exists(file_path):
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                os.remove(file_path)
            else:
                print(f"Error: Audio file '{file_path}' not found")
        except Exception as e:
            print(f"Error playing audio: {e}")