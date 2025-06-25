import os
import base64
import audioop
import asyncio
import logging
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Constants
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1
CHUNK_SIZE = 320  # 20ms of audio at 8kHz

async def send_audio_to_twilio(ws, audio_path):
    try:
        if not os.path.exists(audio_path):
            logger.error(f"[AUDIO → TWILIO] Audio file does not exist: {audio_path}")
            return

        logger.info("[AUDIO → TWILIO] Converting audio to μ-law and streaming...")

        # Load and preprocess
        audio = AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)
        raw_pcm = audio.raw_data

        # --- Send START event ---
        await ws.send_json({
            "event": "start",
            "streamSid": "fake-server-sid",  # Optional: can customize or omit
        })

        # Stream audio in 320-byte μ-law chunks
        for i in range(0, len(raw_pcm), CHUNK_SIZE):
            chunk = raw_pcm[i:i + CHUNK_SIZE]
            ulaw_chunk = audioop.lin2ulaw(chunk, SAMPLE_WIDTH)
            b64_payload = base64.b64encode(ulaw_chunk).decode("utf-8")

            await ws.send_json({
                "event": "media",
                "media": {"payload": b64_payload}
            })
            await asyncio.sleep(0.02)  # pacing

        # --- Send STOP event ---
        await ws.send_json({"event": "stop"})

        logger.info("[AUDIO → TWILIO] Streaming complete.")

    except Exception as e:
        logger.exception(f"[AUDIO → TWILIO] Error during streaming: {e}")
