import os
import base64
import audioop
import asyncio
import logging
import sys
import traceback
from pydub import AudioSegment

# Set up proper console logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Constants
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1
CHUNK_SIZE = 160  # 10ms of audio at 8kHz - smaller for better streaming

async def send_audio_to_twilio(ws, audio_path):
    try:
        if not os.path.exists(audio_path):
            print(f"[AUDIO → TWILIO] ❌ Audio file does not exist: {audio_path}")
            return

        print(f"[AUDIO → TWILIO] 🔄 Converting {audio_path} to μ-law format...")

        # Load and preprocess audio
        audio = AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)
        audio = audio.normalize()
        raw_pcm = audio.raw_data

        print(f"[AUDIO → TWILIO] 📊 Audio length: {len(raw_pcm)} bytes ({len(raw_pcm)/(SAMPLE_RATE*SAMPLE_WIDTH):.2f} seconds)")

        # Stream audio in chunks
        chunks_sent = 0
        for i in range(0, len(raw_pcm), CHUNK_SIZE):
            if ws.client_state.name != "CONNECTED":
                print("[AUDIO → TWILIO] ❌ WebSocket disconnected during streaming")
                break

            chunk = raw_pcm[i:i + CHUNK_SIZE]
            if len(chunk) < CHUNK_SIZE:
                chunk += b'\x00' * (CHUNK_SIZE - len(chunk))

            try:
                ulaw_chunk = audioop.lin2ulaw(chunk, SAMPLE_WIDTH)
                b64_payload = base64.b64encode(ulaw_chunk).decode("utf-8")

                await ws.send_json({
                    "event": "media",
                    "media": {"payload": b64_payload}
                })
                chunks_sent += 1

                if chunks_sent % 50 == 0:
                    print(f"[AUDIO → TWILIO] 🔄 Sent {chunks_sent} chunks")

                await asyncio.sleep(0.02)  # 20ms pacing for reliable streaming

            except Exception as e:
                print(f"[AUDIO → TWILIO] ❌ Error sending chunk {chunks_sent}: {e}")
                break

        print(f"[AUDIO → TWILIO] ✅ Streaming complete! Sent {chunks_sent} chunks")

    except Exception as e:
        print(f"[AUDIO → TWILIO] ❌ Error during streaming: {e}")