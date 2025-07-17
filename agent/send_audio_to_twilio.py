import os
import logging
import sys
import base64
import asyncio
import audioop # Import audioop for ulaw conversion
from pydub import AudioSegment
from fastapi import WebSocket # Import WebSocket for type hinting

# Set up proper console logging (ensure this is only done once)
# Consider moving this to main.py or server.py
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(levelname)s: %(message)s',
#     stream=sys.stdout
# )
logger = logging.getLogger(__name__)

# Constants
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1
CHUNK_SIZE = 160 # Bytes per chunk (8kHz * 16-bit * 1 channel * 0.01 seconds)

async def send_audio_to_twilio(ws: WebSocket, audio_file_path: str):
    """
    Reads an audio file, converts it to Twilio's required format (8kHz, 16-bit, mono, μ-law),
    and streams it over the WebSocket.
    """
    if not audio_file_path or not os.path.exists(audio_file_path):
        logger.error(f"[AUDIO → TWILIO] Error: Audio file not found or path is invalid: {audio_file_path}")
        return

    logger.info(f"[AUDIO → TWILIO] Processing audio file: {audio_file_path}")

    try:
        # Load audio file using pydub
        # pydub requires ffmpeg installed to read mp3
        audio = AudioSegment.from_file(audio_file_path)

        # Convert to 8kHz, 16-bit, mono
        audio = audio.set_frame_rate(SAMPLE_RATE)
        audio = audio.set_sample_width(SAMPLE_WIDTH)
        audio = audio.set_channels(CHANNELS)

        # Export as raw PCM data
        # Use export(format="wav") to get a WAV file object, then read its data
        # This is a common way to get raw PCM from pydub
        from io import BytesIO
        wav_buffer = BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        # Read the WAV header (44 bytes) and then the raw PCM data
        wav_buffer.read(44) # Skip WAV header
        raw_audio_data = wav_buffer.read()


        # Convert PCM to μ-law
        # Ensure audioop is imported
        ulaw_audio_data = audioop.lin2ulaw(raw_audio_data, SAMPLE_WIDTH)

        logger.info(f"[AUDIO → TWILIO] Converted audio to μ-law. Total bytes: {len(ulaw_audio_data)}")

        # --- Add a small delay before streaming starts ---
        logger.info("[AUDIO → TWILIO] Waiting briefly before streaming...")
        await asyncio.sleep(0.1) # Wait 100ms

        # Stream in chunks
        chunks_sent = 0
        for i in range(0, len(ulaw_audio_data), CHUNK_SIZE):
            chunk = ulaw_audio_data[i:i + CHUNK_SIZE]
            payload = base64.b64encode(chunk).decode('utf-8')

            message = {
                "event": "media",
                "media": {
                    "payload": payload
                }
            }
            try:
                # Check if WebSocket is still open before sending
                # Note: This check might not catch immediate closure before the send call itself
                if ws.application_state.name != "CONNECTED" or ws.client_state.name != "CONNECTED":
                    logger.warning("[AUDIO → TWILIO] WebSocket is closed before sending chunk, stopping stream.")
                    break

                # --- Add more specific error handling around send_json ---
                try:
                    await ws.send_json(message)
                    # logger.debug(f"[AUDIO → TWILIO] Sent chunk {chunks_sent + 1}") # Use debug for less verbose logs
                    chunks_sent += 1
                    await asyncio.sleep(0.01) # Small delay to simulate real-time streaming (10ms per chunk)
                except Exception as send_error:
                    logger.error(f"[AUDIO → TWILIO] Error sending chunk {chunks_sent + 1}: {send_error}", exc_info=True) # Log exception details
                    break # Stop streaming on error

            except Exception as outer_error:
                 # This catch is less likely but good practice
                 logger.error(f"[AUDIO → TWILIO] Unexpected error in streaming loop: {outer_error}", exc_info=True)
                 break # Stop streaming on error


        logger.info(f"[AUDIO → TWILIO] Streaming complete! Sent {chunks_sent} chunks.")

    except Exception as e:
        logger.error(f"[AUDIO → TWILIO] Error processing or streaming audio: {e}", exc_info=True) # Log exception details
