import os
import json
import base64
import asyncio
import time
import logging
from fastapi import WebSocket
from services.STT import SpeechToText
from services.TTS import TextToSpeech
from agent.send_audio_to_twilio import send_audio_to_twilio
from langchain_agent import run_agent
from services.GoogleCalendar import GoogleCalendarService
import audioop # <-- ADD THIS IMPORT
from pydub import AudioSegment # <-- ADD THIS IMPORT (needed for WAV header)
from pydub.utils import ratio_to_db # <-- ADD THIS IMPORT (needed for WAV header)


# Set up logging (ensure this doesn't duplicate handlers if main.py sets it up)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     handlers=[logging.StreamHandler()]
# )
logger = logging.getLogger(__name__)

# Constants (might be redundant if defined elsewhere, but safe here)
SAMPLE_WIDTH = 2  # 16-bit PCM # <-- Define constants needed here
SAMPLE_RATE = 8000 # <-- Define constants needed here
# MIN_AUDIO_LENGTH = 8000  # About 0.5 seconds at 8kHz # This constant is defined later, keep it there

# Initialize services
# Ensure these classes are correctly implemented in their respective files
stt = SpeechToText()
tts = TextToSpeech()
calendar_service = GoogleCalendarService()

GREETING = (
    "Hello! This is your real estate appointment assistant. "
    "I'm here to help you schedule a property viewing. "
    "May I know your name and what kind of property you're interested in?"
)

async def handle_twilio_websocket(ws: WebSocket):
    await ws.accept()
    logger.info("Twilio media stream connected.")
    transcript = []
    appointment_booked = False
    lead_info = {
        "name": "", "email": "", "phone": "", "address": "",
        "date": "", "time": "", "calendar_link": ""
    }

    # 1. Greet and introduce
    logger.info(f"Attempting to generate greeting audio: '{GREETING}'")
    greeting_audio_path = tts.speak(GREETING)

    if not greeting_audio_path or not os.path.exists(greeting_audio_path) or os.path.getsize(greeting_audio_path) == 0:
        logger.error(f"TTS failed to generate greeting audio or file is empty: {greeting_audio_path}")
        # Send a fallback message or close the connection gracefully
        fallback_msg = "Sorry, I'm having trouble with my voice. Please try again later."
        fallback_audio_path = tts.speak(fallback_msg)
        if fallback_audio_path and os.path.exists(fallback_audio_path) and os.path.getsize(fallback_audio_path) > 0:
             await send_audio_to_twilio(ws, fallback_audio_path)
        await ws.close(code=1011) # Internal Error
        return # Stop processing this call
    else:
        logger.info(f"Greeting audio generated successfully at: {greeting_audio_path}")
        logger.info(f"File size: {os.path.getsize(greeting_audio_path)} bytes")

    logger.info("Sending greeting audio to Twilio...")
    await send_audio_to_twilio(ws, greeting_audio_path)
    logger.info("Greeting audio sent.")
    transcript.append(f"Agent: {GREETING}")

    # Define minimum audio length for transcription (e.g., 0.5 seconds * 8000 samples/sec * 2 bytes/sample)
    MIN_AUDIO_LENGTH_BYTES = 8000 # This constant was already here, good.

    try:
        while not appointment_booked:
            # 2. Receive user speech robustly (wait up to 30 seconds for input)
            audio_buffer = bytearray()
            stop_received = False
            timeout_counter = 0
            logger.info("Waiting for user audio...")

            # Loop to collect audio chunks
            while not stop_received:
                try:
                    # Wait for a message with a timeout
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0) # Wait 2 seconds per chunk

                    if msg.get("event") == "media":
                        payload = msg["media"]["payload"]
                        audio_data = base64.b64decode(payload)
                        audio_buffer.extend(audio_data)
                        timeout_counter = 0 # Reset timeout on receiving media
                        # logger.debug(f"Received {len(audio_data)} bytes of audio. Total buffer: {len(audio_buffer)}")

                        # Process audio if buffer is large enough (e.g., 2 seconds of audio)
                        # Twilio streams ulaw 8kHz 1-channel. 2 seconds is 2 * 8000 * 1 = 16000 bytes
                        if len(audio_buffer) >= 16000:
                             logger.info(f"Collected {len(audio_buffer)} bytes of audio. Processing...")
                             break # Exit inner loop to process audio

                    elif msg.get("event") == "stop":
                        logger.info("Stream stopped by Twilio.")
                        stop_received = True
                        break
                    elif msg.get("event") == "start":
                         logger.info("Received start event during conversation loop.")
                    elif msg.get("event") == "mark":
                         logger.info(f"Received mark event: {msg.get('mark')}")

                except asyncio.TimeoutError:
                    timeout_counter += 1
                    logger.debug(f"Timeout waiting for media. Counter: {timeout_counter}")
                    if timeout_counter * 2.0 > 30.0: # Wait up to 30 seconds for user input
                        logger.info("No user audio received within timeout, ending call.")
                        stop_received = True
                        break
                except Exception as e:
                    logger.error(f"Error receiving message from WebSocket: {e}", exc_info=True) # Log exception details
                    stop_received = True
                    break # Exit inner loop on error

            if stop_received:
                 logger.info("Stopping conversation loop due to stop event or error.")
                 break # Exit main conversation loop

            if not audio_buffer or len(audio_buffer) < MIN_AUDIO_LENGTH_BYTES:
                logger.info(f"Audio buffer too short ({len(audio_buffer)} bytes), waiting for more speech or ending.")
                # If we timed out or got a stop with insufficient audio, break
                if timeout_counter * 2.0 > 30.0 or stop_received:
                     break
                continue # Otherwise, continue waiting for more audio

            # 3. Transcribe user input
            # Twilio streams ulaw 8kHz 1-channel. Need to convert to 16-bit PCM for Whisper STT.
            try:
                # Convert ulaw to 16-bit linear PCM
                # Ensure audioop is imported at the top
                pcm_audio_data = audioop.ulaw2lin(audio_buffer, SAMPLE_WIDTH)

                # Save PCM to WAV for STT
                wav_path = "temp_input.wav"
                # Need to add WAV header to the PCM data using pydub
                # Ensure pydub and its utilities are imported at the top
                audio_segment = AudioSegment(
                    pcm_audio_data,
                    sample_width=SAMPLE_WIDTH,
                    frame_rate=SAMPLE_RATE,
                    channels=1
                )
                audio_segment.export(wav_path, format="wav")

                logger.info(f"Saved user audio to {wav_path} ({os.path.getsize(wav_path)} bytes)")

                user_text = stt.transcribe(wav_path)
                logger.info(f"User said: {user_text}")
                transcript.append(f"User: {user_text}")

                if not user_text.strip():
                    reprompt = "Sorry, I didn't catch that. Could you please repeat?"
                    reprompt_audio = tts.speak(reprompt)
                    await send_audio_to_twilio(ws, reprompt_audio)
                    transcript.append(f"Agent: {reprompt}")
                    continue

            except Exception as e:
                 logger.error(f"Error during transcription: {e}", exc_info=True) # Log exception details
                 reprompt = "Sorry, I had trouble understanding you. Could you please repeat?"
                 reprompt_audio = tts.speak(reprompt)
                 await send_audio_to_twilio(ws, reprompt_audio)
                 transcript.append(f"Agent: {reprompt}")
                 continue # Continue the loop to try again

            # 4. Generate agent response and extract info
            ai_response = run_agent(user_text)
            logger.info(f"Agent replied: {ai_response}")
            transcript.append(f"Agent: {ai_response}")

            # 5. Check for appointment intent and extract details
            # Expecting LangChain agent to output a JSON block with appointment info when ready
            if "appointment confirmed" in ai_response.lower() or "appointment booked" in ai_response.lower():
                logger.info("Appointment booking intent detected.")
                # Try to extract info from the response (assume JSON block at end)
                try:
                    start = ai_response.index("{")
                    end = ai_response.rindex("}") + 1
                    info_json = ai_response[start:end]
                    # Use json.loads if your agent outputs strict JSON, eval is risky
                    info = json.loads(info_json)
                    lead_info.update(info)
                    logger.info(f"Extracted lead info: {lead_info}")
                except Exception as e:
                    logger.warning(f"Could not extract appointment info from agent response: {e}", exc_info=True) # Log exception details
                    # Fallback: Ask the user for details if extraction failed
                    fallback_ask = "Could you please confirm your name, email, phone number, address, and preferred appointment time?"
                    fallback_audio = tts.speak(fallback_ask)
                    await send_audio_to_twilio(ws, fallback_audio)
                    transcript.append(f"Agent: {fallback_ask}")
                    continue # Continue the loop to get details

                # Book appointment
                try:
                    # Basic validation before booking
                    if not all([lead_info.get('name'), lead_info.get('email'), lead_info.get('date'), lead_info.get('time')]):
                         logger.warning("Missing required info for booking.")
                         missing_info_msg = "I seem to be missing some details like your name, email, date, or time. Could you please provide them?"
                         missing_info_audio = tts.speak(missing_info_msg)
                         await send_audio_to_twilio(ws, missing_info_audio)
                         transcript.append(f"Agent: {missing_info_msg}")
                         continue # Continue the loop to get missing info

                    summary = f"Viewing with {lead_info.get('name', 'Lead')}"
                    description = f"Phone: {lead_info.get('phone', 'N/A')}\nAddress: {lead_info.get('address', 'N/A')}"
                    # Ensure date and time are in correct format (YYYY-MM-DDTHH:MM:SS)
                    # You might need more robust date/time parsing here
                    start_time_str = info.get('date') + 'T' + info.get('time') + ':00' # Example format
                    # Calculate end time (e.g., +30 mins)
                    from datetime import datetime, timedelta
                    try:
                        start_dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
                        end_dt = start_dt + timedelta(minutes=30)
                        end_time_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    except ValueError:
                        logger.error(f"Could not parse date/time format: {start_time_str}. Using simple string concatenation.", exc_info=True) # Log exception details
                        end_time_str = f"{info.get('date')}T{info.get('time')}:30" # Fallback (less reliable)

                    attendees = [info.get('email')]

                    logger.info(f"Attempting to book appointment: Summary='{summary}', Start='{start_time_str}', End='{end_time_str}', Attendees='{[lead_info.get('email')]}'")

                    link = calendar_service.create_appointment(
                        summary, description, start_time_str, end_time_str, attendees
                    )
                    lead_info["calendar_link"] = link
                    logger.info(f"Appointment booked successfully. Link: {link}")

                    closing = (
                        f"Your appointment is booked! You'll receive a confirmation at {lead_info.get('email', 'your email')}. "
                        "Thank you for your time. Goodbye!"
                    )
                    closing_audio = tts.speak(closing)
                    await send_audio_to_twilio(ws, closing_audio)
                    transcript.append(f"Agent: {closing}")
                    appointment_booked = True # Exit loop after booking
                    break # Ensure loop breaks

                except Exception as e:
                    logger.error(f"Failed to book appointment: {e}", exc_info=True) # Log exception details
                    error_msg = "Sorry, I was unable to book your appointment. Please try again later."
                    error_audio = tts.speak(error_msg)
                    await send_audio_to_twilio(ws, error_audio)
                    transcript.append(f"Agent: {error_msg}")
                    # Decide whether to break or continue the conversation after booking failure
                    # For now, let's break to avoid infinite loop on booking error
                    break


            # 6. Speak agent response (if not booking)
            else:
                response_audio = tts.speak(ai_response)
                await send_audio_to_twilio(ws, response_audio)

    except Exception as e:
        logger.error(f"WebSocket error during conversation: {e}", exc_info=True) # Log exception details

    finally:
        logger.info("Call ended. Saving transcript and lead info.")
        # Save transcript and lead info
        ts = int(time.time())
        try:
            with open(f"call_transcript_{ts}.txt", "w", encoding="utf-8") as f:
                for line in transcript:
                    f.write(line + "\n")
            logger.info(f"Transcript saved to call_transcript_{ts}.txt")
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}", exc_info=True) # Log exception details

        try:
            with open(f"lead_info_{ts}.json", "w", encoding="utf-8") as f:
                json.dump(lead_info, f, indent=2)
            logger.info(f"Lead info saved to lead_info_{ts}.json")
        except Exception as e:
            logger.error(f"Failed to save lead info: {e}", exc_info=True) # Log exception details

        logger.info("Full call transcript:")
        for line in transcript:
            logger.info(line)
        logger.info(f"Final Lead info: {lead_info}")

        # Ensure WebSocket is closed
        if ws.application_state.name == "CONNECTED" or ws.client_state.name == "CONNECTED":
             try:
                 await ws.close()
                 logger.info("WebSocket closed.")
             except Exception as e:
                 logger.error(f"Error closing WebSocket: {e}", exc_info=True) # Log exception details
