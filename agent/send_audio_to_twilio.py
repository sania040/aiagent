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

        # Load audio with explicit format detection
        try:
            # Detect format from file extension
            format = os.path.splitext(audio_path)[1].replace('.', '')
            print(f"[AUDIO → TWILIO] 📂 Detected format: {format}")
            
            # Load and preprocess with explicit format
            audio = AudioSegment.from_file(audio_path, format=format)
            
            # Convert to PCM with required parameters
            print(f"[AUDIO → TWILIO] ⚙️ Converting to PCM: {SAMPLE_RATE}Hz, {CHANNELS} channel(s), {SAMPLE_WIDTH*8}-bit")
            audio = audio.set_frame_rate(SAMPLE_RATE)
            audio = audio.set_channels(CHANNELS)
            audio = audio.set_sample_width(SAMPLE_WIDTH)
            
            # Normalize audio volume for better audibility
            audio = audio.normalize()
            raw_pcm = audio.raw_data
            
            print(f"[AUDIO → TWILIO] 📊 Audio length: {len(raw_pcm)} bytes ({len(raw_pcm)/(SAMPLE_RATE*SAMPLE_WIDTH*CHANNELS):.2f} seconds)")
        
        except Exception as e:
            print(f"[AUDIO → TWILIO] ❌ Error converting audio: {e}")
            return

        # Check if WebSocket is still open before streaming
        if ws.client_state.name != "CONNECTED":
            print("[AUDIO → TWILIO] ❌ WebSocket not connected")
            return

        # Mark the start of streaming
        try:
            await ws.send_json({
                "event": "mark",
                "mark": {"name": "audio_start"}
            })
        except Exception as e:
            print(f"[AUDIO → TWILIO] ❌ WebSocket error before streaming: {e}")
            return
        
        print("[AUDIO → TWILIO] 📢 Starting audio streaming...")

        # Stream audio in smaller chunks with better error handling
        chunks_sent = 0
        total_chunks = len(raw_pcm) // CHUNK_SIZE
        
        # Reduce audio length if it's too long (cap at ~8 seconds)
        max_chunks = min(total_chunks, 400)  # ~8 seconds at 8kHz
        if max_chunks < total_chunks:
            print(f"[AUDIO → TWILIO] ⚠️ Audio too long, trimming to {max_chunks*CHUNK_SIZE/(SAMPLE_RATE*SAMPLE_WIDTH):.1f} seconds")
        
        for i in range(0, min(len(raw_pcm), max_chunks * CHUNK_SIZE), CHUNK_SIZE):
            # Check connection before each chunk
            if ws.client_state.name != "CONNECTED":
                print("[AUDIO → TWILIO] ❌ WebSocket disconnected during streaming")
                break
                
            chunk = raw_pcm[i:i + CHUNK_SIZE]
            if len(chunk) < CHUNK_SIZE:
                # Pad the last chunk if necessary
                chunk += b'\x00' * (CHUNK_SIZE - len(chunk))
            
            try:
                # Convert to μ-law format
                ulaw_chunk = audioop.lin2ulaw(chunk, SAMPLE_WIDTH)
                b64_payload = base64.b64encode(ulaw_chunk).decode("utf-8")

                # Send the audio chunk
                await ws.send_json({
                    "event": "media",
                    "media": {"payload": b64_payload}
                })
                chunks_sent += 1
                
                # Progress indicator every 50 chunks
                if chunks_sent % 50 == 0:
                    print(f"[AUDIO → TWILIO] 🔄 Sent {chunks_sent}/{max_chunks} chunks ({chunks_sent/max_chunks*100:.0f}%)")
                
                # Slower pacing for more reliable streaming (25ms per chunk)
                await asyncio.sleep(0.025)  # Slower pacing to prevent disconnect
                
            except RuntimeError as re:
                if "close message has been sent" in str(re):
                    print("[AUDIO → TWILIO] ℹ️ WebSocket closed by remote - stopping audio stream")
                    break
                else:
                    print(f"[AUDIO → TWILIO] ❌ Error sending chunk {chunks_sent}: {re}")
                    break
            except Exception as chunk_error:
                print(f"[AUDIO → TWILIO] ❌ Error sending chunk {chunks_sent}: {chunk_error}")
                break

        # Try to send end mark if still connected
        try:
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({
                    "event": "mark",
                    "mark": {"name": "audio_end"}
                })
                print(f"[AUDIO → TWILIO] ✅ Streaming complete! Sent {chunks_sent} chunks ({chunks_sent*CHUNK_SIZE/(SAMPLE_RATE*SAMPLE_WIDTH):.2f} seconds)")
            else:
                print(f"[AUDIO → TWILIO] ⚠️ WebSocket closed after sending {chunks_sent} chunks")
        except Exception as e:
            print("[AUDIO → TWILIO] ℹ️ Could not send end mark (connection likely closed)")

    except Exception as e:
        print(f"[AUDIO → TWILIO] ❌ Error during streaming: {e}")
        traceback.print_exc()