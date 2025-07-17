import os
import tempfile
import logging
from dotenv import load_dotenv
import openai
from tenacity import retry, stop_after_attempt, wait_exponential # Import retry decorators

logger = logging.getLogger(__name__)

class TextToSpeech:
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            logger.error("OPENAI_API_KEY not found in environment variables.")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _generate_speech_with_retry(self, text, voice="alloy"):
        """Internal method with retry logic for OpenAI API call."""
        logger.debug(f"Attempting OpenAI TTS for text: '{text[:50]}...'")
        # Add explicit timeout as suggested by boss
        response = openai.audio.speech.create(
            model="tts-1", # Using tts-1 as in your code, boss suggested tts-1-hd (can change if needed)
            voice=voice,
            input=text,
            timeout=10 # Add explicit timeout in seconds
        )
        logger.debug("OpenAI TTS call successful.")
        return response

    def speak(self, text, output_path=None, voice="alloy"):
        """
        Generate speech from text using OpenAI TTS, save to output_path (mp3), and return the file path.
        If output_path is None, a temp file is created and its path is returned.
        Includes retry logic.
        """
        if not openai.api_key:
            logger.error("OpenAI API key is not set. Cannot generate speech.")
            return None

        if not text:
            logger.warning("No text provided for TTS.")
            return None

        try:
            # Call the internal method with retry logic
            response = self._generate_speech_with_retry(text, voice=voice)

            if output_path is None:
                # Create a temporary file with .mp3 suffix
                fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd) # Close the file descriptor immediately
                output_path = temp_path
                logger.debug(f"Created temporary file for TTS: {output_path}")

            # Write the audio content to the file
            response.write_to_file(output_path)
            logger.debug(f"TTS audio saved to {output_path}")

            return output_path

        except Exception as e:
            # The retry decorator will handle retries, this catch is for final failure
            logger.error(f"Final attempt failed: Error generating speech with OpenAI TTS: {e}")
            return None

    # Removed play_audio as it's not needed for the Twilio pipeline
    # Removed pygame imports as they are not needed for server-side TTS