import json, base64, wave, audioop
import asyncio
import tempfile
import os
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from services.STT import SpeechToText
from services.TextGen import TextGenerator
from services.TTS import TextToSpeech
from services.ConversationExtractor import ConversationExtractor
from agent.send_audio_to_twilio import send_audio_to_twilio

SAMPLE_WIDTH = 2  # 16-bit PCM
SAMPLE_RATE = 8000
CHANNELS = 1

stt = SpeechToText()
textgen = TextGenerator()
tts = TextToSpeech()
extractor = ConversationExtractor()

def websocket_is_open(ws: WebSocket) -> bool:
    return ws.application_state.name == "CONNECTED" and ws.client_state.name == "CONNECTED"

async def handle_twilio_websocket(ws: WebSocket):
    try:
        await ws.accept()
        print("[WEBSOCKET] Connected to Twilio media stream...")

        pcm_frames = bytearray()
        temp_audio_file = None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            temp_audio_file = tmp_file.name
            print(f"[AUDIO] Using temporary file: {temp_audio_file}")

        async for msg in ws.iter_text():
            data = json.loads(msg)

            if data["event"] == "start":
                print("[MEDIA] Stream started")
            elif data["event"] == "media":
                try:
                    mulaw_data = base64.b64decode(data["media"]["payload"])
                    pcm_chunk = audioop.ulaw2lin(mulaw_data, SAMPLE_WIDTH)
                    pcm_frames.extend(pcm_chunk)
                except Exception as decode_err:
                    print(f"[ERROR] Failed to decode audio: {decode_err}")
                    continue
            elif data["event"] == "stop":
                print("[MEDIA] Stream stopped")
                break

        if pcm_frames:
            with wave.open(temp_audio_file, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(SAMPLE_WIDTH)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm_frames)

            print(f"[AUDIO] Saved audio to {temp_audio_file}")

            try:
                if len(pcm_frames) < 3200:
                    print("[AUDIO] Audio too short, skipping transcription.")
                    return

                print("[PROCESSING] Starting transcription...")
                transcript = await asyncio.to_thread(stt.transcribe_audio, temp_audio_file)
                if not transcript:
                    print("[ERROR] Transcription failed or returned nothing.")
                    return
                print(f"[TRANSCRIPT] Received: {transcript}")

                print("[PROCESSING] Starting text generation...")
                response = await asyncio.to_thread(textgen.generate_response, transcript)
                print(f"[RESPONSE] Received: {response}")

                print("[PROCESSING] Extracting information...")
                info = await asyncio.to_thread(extractor.extract_information, transcript, response)
                print(f"[EXTRACTED INFO] Received: {info}" if any(info.values()) else "[EXTRACTED INFO] Nothing extracted.")

                print("[PROCESSING] Generating speech...")
                speech_path = await asyncio.to_thread(tts.generate_speech, response, voice="nova")
                if speech_path:
                    print(f"[TTS] Generated speech file: {speech_path}")
                    try:
                        await send_audio_to_twilio(ws, speech_path)
                    except WebSocketDisconnect:
                        print("[AUDIO → TWILIO] WebSocket disconnected during audio send.")
                    except Exception as e:
                        print(f"[AUDIO → TWILIO] Error during audio stream: {e}")
                    finally:
                        if os.path.exists(speech_path):
                            os.remove(speech_path)
                            print(f"[TTS] Cleaned up speech file: {speech_path}")
                else:
                    print("[TTS] No speech file generated.")

            except Exception as e:
                import traceback
                print(f"[PIPELINE ERROR] {e}")
                traceback.print_exc()

        else:
            print("[AUDIO] No audio data received.")

    except Exception as e:
        import traceback
        print(f"[WEBSOCKET ERROR] {e}")
        traceback.print_exc()

    finally:
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.remove(temp_audio_file)
                print(f"[AUDIO] Cleaned up temporary file: {temp_audio_file}")
            except OSError as e:
                print(f"[CLEANUP ERROR] {e}")

        try:
            if websocket_is_open(ws):
                await ws.close()
        except Exception as e:
            print(f"[WEBSOCKET CLOSE ERROR] {e}")

        print("[WEBSOCKET] Connection closed.")
