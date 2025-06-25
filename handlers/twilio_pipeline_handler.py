import json
import base64
import wave
import audioop
import asyncio
import tempfile
import os
import logging
from fastapi import WebSocket
from services.STT import SpeechToText
from services.TextGen import TextGenerator
from services.TTS import TextToSpeech
from services.ConversationExtractor import ConversationExtractor
from agent.send_audio_to_twilio import send_audio_to_twilio

# Logging setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Audio settings (Twilio defaults)
SAMPLE_WIDTH = 2  # 16-bit PCM
SAMPLE_RATE = 8000
CHANNELS = 1
MIN_AUDIO_LENGTH = 3200  # ~0.5 seconds at 8000 Hz

# Initialize services
stt = SpeechToText()
textgen = TextGenerator()
tts = TextToSpeech()
extractor = ConversationExtractor()

async def handle_twilio_websocket(ws: WebSocket):
    connected = False
    temp_audio_file = None

    try:
        await ws.accept()
        connected = True
        logger.info("[WEBSOCKET] Connected to Twilio media stream.")

        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            temp_audio_file = tmp_file.name
            logger.info(f"[AUDIO] Using temporary file: {temp_audio_file}")

        pcm_frames = bytearray()

        async for msg in ws.iter_text():
            data = json.loads(msg)

            if data["event"] == "start":
                start_info = data.get("start", {})
                logger.info(f"[MEDIA] Stream started — Call SID: {start_info.get('callSid')}")

            elif data["event"] == "media":
                payload = data["media"]["payload"]
                try:
                    mulaw_data = base64.b64decode(payload)
                    pcm_chunk = audioop.ulaw2lin(mulaw_data, SAMPLE_WIDTH)
                    pcm_frames.extend(pcm_chunk)
                except Exception as decode_err:
                    logger.error(f"[ERROR] Failed to decode audio chunk: {decode_err}")
                    continue

            elif data["event"] == "stop":
                logger.info("[MEDIA] Stream stopped.")
                break

        # Process the collected audio
        if not pcm_frames:
            logger.warning("[AUDIO] No audio data received from stream.")
            return

        if len(pcm_frames) < MIN_AUDIO_LENGTH:
            logger.warning("[AUDIO] Audio too short, skipping transcription.")
            return

        # Save to WAV
        with wave.open(temp_audio_file, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_frames)
        logger.info(f"[AUDIO] Saved audio to {temp_audio_file}")

        # Transcribe
        logger.info("[PROCESSING] Transcribing audio...")
        transcript = await asyncio.to_thread(stt.transcribe_audio, temp_audio_file)
        if not transcript:
            logger.error("[TRANSCRIPT] Failed or empty.")
            return
        logger.info(f"[TRANSCRIPT] {transcript}")

        # Generate response
        logger.info("[PROCESSING] Generating response...")
        response = await asyncio.to_thread(textgen.generate_response, transcript)
        if not response:
            logger.error("[TEXTGEN] Failed to generate response.")
            return
        logger.info(f"[RESPONSE] {response}")

        # Extract info
        logger.info("[PROCESSING] Extracting information...")
        info = await asyncio.to_thread(extractor.extract_information, transcript, response)
        if any(info.values()):
            logger.info(f"[EXTRACTED INFO] {info}")
        else:
            logger.info("[EXTRACTED INFO] Nothing extracted.")

        # Text-to-Speech
        logger.info("[PROCESSING] Generating speech...")
        speech_path = await asyncio.to_thread(tts.generate_speech, response, voice="nova")
        if not speech_path:
            logger.error("[TTS] Failed to generate speech.")
            return

        logger.info(f"[TTS] Generated: {speech_path}")
        await send_audio_to_twilio(ws, speech_path)

        # Clean up generated audio
        if os.path.exists(speech_path):
            os.remove(speech_path)
            logger.info(f"[CLEANUP] Deleted generated speech file: {speech_path}")

    except Exception as e:
        logger.exception(f"[WEBSOCKET ERROR] {e}")

    finally:
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.remove(temp_audio_file)
                logger.info(f"[CLEANUP] Deleted temporary file: {temp_audio_file}")
            except OSError as err:
                logger.warning(f"[CLEANUP] Error deleting {temp_audio_file}: {err}")

        if connected:
            await ws.close()
            logger.info("[WEBSOCKET] Connection closed.")
