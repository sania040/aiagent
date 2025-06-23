import base64
import audioop
import asyncio
from pydub import AudioSegment

async def send_audio_to_twilio(ws, audio_path):
    try:
        print("[AUDIO → TWILIO] Converting audio to μ-law and streaming...")
        
        # convert mp3 to raw PCM (16-bit, 8kHz, mono)
        audio = AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        raw_pcm = audio.raw_data

        # break into 320-byte chunks (20ms @ 8kHz mono, 16-bit)
        for i in range(0, len(raw_pcm), 320):
            chunk = raw_pcm[i:i+320]
            ulaw_chunk = audioop.lin2ulaw(chunk, 2)  # 2 bytes = 16-bit
            b64_payload = base64.b64encode(ulaw_chunk).decode("utf-8")

            msg = {
                "event": "media",
                "media": {
                    "payload": b64_payload
                }
            }

            await ws.send_json(msg)
            await asyncio.sleep(0.02)  # 20ms pacing

        print("[AUDIO → TWILIO] Streaming complete.")

    except Exception as e:
        print(f"[AUDIO → TWILIO] Error: {e}")
