import os
from dotenv import load_dotenv
import openai
import logging

logger = logging.getLogger(__name__)

class SpeechToText:
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            logger.error("OPENAI_API_KEY not found in environment variables.")

    def transcribe(self, audio_file_path):
        """
        Transcribes audio from a file using OpenAI's Whisper API.
        audio_file_path should be a path to a WAV or other supported audio file.
        """
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file not found for transcription: {audio_file_path}")
            return ""
        if os.path.getsize(audio_file_path) == 0:
             logger.warning(f"Audio file is empty, cannot transcribe: {audio_file_path}")
             return ""

        try:
            with open(audio_file_path, "rb") as audio_file:
                # Use the whisper-1 model
                response = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
                # The response object has a 'text' attribute
                transcribed_text = response.text
                logger.info(f"Transcription successful: {transcribed_text}")
                return transcribed_text
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return ""
