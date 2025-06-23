# handlers/twilio_pipeline_handler.py

import json, base64, wave, audioop
from fastapi import WebSocket
from services.STT import SpeechToText
from services.TextGen import TextGenerator
from services.TTS import TextToSpeech
from services.ConversationExtractor import ConversationExtractor
from agent.send_audio_to_twilio import send_audio_to_twilio

AUDIO_FILE = "output.wav"
SAMPLE_WIDTH = 2  # 16-bit PCM
SAMPLE_RATE = 8000
CHANNELS = 1

stt = SpeechToText()
textgen = TextGenerator()
tts = TextToSpeech()
extractor = ConversationExtractor()

async def handle_twilio_websocket(ws: WebSocket):
    await ws.accept()
    print("[WEBSOCKET] Connected to Twilio media stream...")

    try:
        pcm_frames = bytearray()

        async for msg in ws.iter_text():
            data = json.loads(msg)

            if data["event"] == "start":
                print("[MEDIA] Stream started")
            elif data["event"] == "media":
                payload = data["media"]["payload"]
                mulaw_data = base64.b64decode(payload)
                pcm_chunk = audioop.ulaw2lin(mulaw_data, SAMPLE_WIDTH)
                pcm_frames.extend(pcm_chunk)
            elif data["event"] == "stop":
                print("[MEDIA] Stream stopped")
                break

        with wave.open(AUDIO_FILE, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_frames)

        print(f"[AUDIO] Saved audio to {AUDIO_FILE}")

        try:
            transcript = stt.transcribe_audio(AUDIO_FILE)
            print("[TRANSCRIPT]", transcript)

            response = textgen.generate_response(transcript)
            print("[RESPONSE]", response)

            info = extractor.extract_information(transcript, response)
            if any(info.values()):
                print("[EXTRACTED INFO]", info)

            speech_path = tts.generate_speech(response, voice="nova")
            if speech_path:
                await send_audio_to_twilio(ws, speech_path)

        except Exception as e:
            print(f"[ERROR in processing audio] {e}")

    except Exception as e:
        print(f"[WEBSOCKET ERROR] {e}")

    await ws.close()
    print("[WEBSOCKET] Connection closed.")
