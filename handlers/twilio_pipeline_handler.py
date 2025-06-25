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
from collections import deque
import time

SAMPLE_WIDTH = 2  # 16-bit PCM
SAMPLE_RATE = 8000
CHANNELS = 1
MIN_AUDIO_LENGTH = 8000  # About 0.5 seconds at 8kHz

# Voice activity detection settings
VAD_WINDOW = 10  # Number of frames to check for voice activity
VAD_ENERGY_THRESHOLD = 200  # Energy threshold for voice activity
MAX_SILENCE_DURATION = 1.5  # Process after 1.5 seconds of silence
MIN_SPEECH_DURATION = 1.0  # Minimum speech duration before processing

stt = SpeechToText()
textgen = TextGenerator()
tts = TextToSpeech()
extractor = ConversationExtractor()

def websocket_is_open(ws: WebSocket) -> bool:
    return ws.application_state.name == "CONNECTED" and ws.client_state.name == "CONNECTED"

def calculate_energy(pcm_data):
    """Calculate audio energy (loudness)"""
    if not pcm_data:
        return 0
    # Use audioop to calculate RMS (root mean square) of the audio chunk
    return audioop.rms(pcm_data, SAMPLE_WIDTH)

class SmartVoiceCollector:
    """Smart voice activity detector and collector"""
    
    def __init__(self):
        self.pcm_frames = bytearray()
        self.energy_window = deque(maxlen=VAD_WINDOW)
        self.speech_detected = False
        self.speech_start_time = 0
        self.last_speech_time = 0
        self.silence_streak = 0
        self.speech_frames = 0
        self.stream_started = False
        
    def process_audio_chunk(self, chunk):
        """Process an audio chunk and detect speech/silence"""
        if not chunk:
            self.silence_streak += 1
            return
            
        # Add chunk to collected frames
        self.pcm_frames.extend(chunk)
        
        # Calculate energy and update window
        energy = calculate_energy(chunk)
        self.energy_window.append(energy)
        
        # Detect speech activity
        avg_energy = sum(self.energy_window) / len(self.energy_window) if self.energy_window else 0
        is_speech = avg_energy > VAD_ENERGY_THRESHOLD
        
        if is_speech:
            if not self.speech_detected:
                self.speech_detected = True
                self.speech_start_time = time.time()
                print("[VAD] 🎙️ Speech detected!")
            
            self.last_speech_time = time.time()
            self.silence_streak = 0
            self.speech_frames += 1
        else:
            self.silence_streak += 1
            
    def should_process(self):
        """Determine if we should process the collected audio"""
        # No speech detected at all
        if not self.speech_detected:
            return False
            
        # Calculate silence duration since last speech
        silence_duration = time.time() - self.last_speech_time if self.last_speech_time else 0
        speech_duration = self.last_speech_time - self.speech_start_time if self.speech_start_time else 0
        
        # If we have a significant silence after meaningful speech, process it
        if silence_duration > MAX_SILENCE_DURATION and speech_duration > MIN_SPEECH_DURATION:
            print(f"[VAD] ✅ Processing: {speech_duration:.1f}s speech + {silence_duration:.1f}s silence")
            return True
            
        # If we have lots of speech frames, process anyway (long monologue)
        if self.speech_frames > 800:  # ~10 seconds of continuous speech
            print(f"[VAD] ⏱️ Long speech detected ({self.speech_frames} frames)")
            return True
            
        return False
        
    def reset(self):
        """Reset state but keep the PCM frames"""
        self.speech_detected = False
        self.speech_start_time = 0
        self.last_speech_time = 0
        self.silence_streak = 0
        self.speech_frames = 0

async def collect_speech_smartly(ws):
    """Collect speech with smart voice activity detection"""
    collector = SmartVoiceCollector()
    max_wait_time = 10.0  # Maximum wait time without any activity
    last_activity_time = time.time()
    data_received = False
    
    try:
        while websocket_is_open(ws):
            # Create a task to get the next message with a short timeout
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                last_activity_time = time.time()
                
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("[ERROR] Invalid JSON received")
                    continue
                
                if data["event"] == "start":
                    print("[MEDIA] 🌟 Stream started")
                    collector.stream_started = True
                    data_received = True
                    # Send a mark to indicate we're ready
                    await ws.send_json({
                        "event": "mark",
                        "mark": {"name": "ready"}
                    })
                    
                elif data["event"] == "media" and collector.stream_started:
                    try:
                        payload = data["media"]["payload"]
                        if payload:
                            mulaw_data = base64.b64decode(payload)
                            pcm_chunk = audioop.ulaw2lin(mulaw_data, SAMPLE_WIDTH)
                            collector.process_audio_chunk(pcm_chunk)
                            data_received = True
                            
                            # Check if we should process based on voice activity
                            if collector.should_process():
                                # We have speech followed by silence - break to process
                                return collector.pcm_frames, data_received, True
                    except Exception as e:
                        print(f"[ERROR] Failed to process audio chunk: {e}")
                        
                elif data["event"] == "stop":
                    print("[MEDIA] 🛑 Stream stopped")
                    # Process whatever we have
                    return collector.pcm_frames, data_received, True
                    
                elif data["event"] == "mark":
                    mark_name = data.get("mark", {}).get("name")
                    print(f"[MARK] 🏷️ Received mark: {mark_name}")
                    
            except asyncio.TimeoutError:
                # Check if we should process what we have
                if collector.should_process():
                    return collector.pcm_frames, data_received, True
                    
                # Check for inactivity timeout
                if time.time() - last_activity_time > max_wait_time:
                    print(f"[VAD] ⏰ Timeout after {max_wait_time}s of inactivity")
                    return collector.pcm_frames, data_received, True
                    
            except Exception as e:
                print(f"[ERROR] WebSocket error: {e}")
                break
                
    except Exception as e:
        print(f"[ERROR] Collection error: {e}")
        
    return collector.pcm_frames, data_received, True

async def handle_twilio_websocket(ws: WebSocket):
    try:
        await ws.accept()
        print("[WEBSOCKET] 🔌 Connected to Twilio media stream...")

        # Keep conversation going until disconnect
        conversation_active = True
        
        while conversation_active and websocket_is_open(ws):
            temp_audio_file = None

            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    temp_audio_file = tmp_file.name
                    print(f"[AUDIO] 📁 Using temporary file: {temp_audio_file}")

                # Collect audio with smart voice detection
                pcm_frames, data_received, should_continue = await collect_speech_smartly(ws)
                
                if not should_continue:
                    conversation_active = False
                    break
                
                if not data_received:
                    print("[WEBSOCKET] No data received, ending conversation")
                    conversation_active = False
                    break

                # Process the collected audio
                if pcm_frames and len(pcm_frames) >= MIN_AUDIO_LENGTH and websocket_is_open(ws):
                    # Save audio to file
                    try:
                        with wave.open(temp_audio_file, "wb") as wf:
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(SAMPLE_WIDTH)
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(pcm_frames)
                        
                        print(f"[AUDIO] 💾 Saved {len(pcm_frames)} bytes ({len(pcm_frames)/SAMPLE_RATE/SAMPLE_WIDTH:.1f}s audio)")
                        
                        # Process audio through the pipeline with error handling
                        try:
                            print("[STT] 🔊 Starting transcription...")
                            transcript = await asyncio.wait_for(
                                asyncio.to_thread(stt.transcribe_audio, temp_audio_file), 
                                timeout=15.0
                            )
                            
                            if transcript and transcript.strip():
                                print(f"[TRANSCRIPT] 📝 Received: {transcript}")
                                
                                print("[TEXTGEN] 🧠 Generating response...")
                                response = await asyncio.wait_for(
                                    asyncio.to_thread(textgen.generate_response, transcript),
                                    timeout=10.0
                                )
                                print(f"[RESPONSE] 💬 Generated: {response}")
                                
                                # Extract information (non-blocking)
                                asyncio.create_task(
                                    asyncio.to_thread(extractor.extract_information, transcript, response)
                                )
                                
                                # Generate and send speech response
                                if websocket_is_open(ws):
                                    print("[TTS] 🗣️ Generating speech...")
                                    speech_path = await asyncio.wait_for(
                                        asyncio.to_thread(tts.generate_speech, response, voice="nova"),
                                        timeout=15.0
                                    )
                                    
                                    if speech_path and os.path.exists(speech_path):
                                        print(f"[TTS] 🔉 Generated speech file: {speech_path}")
                                        
                                        # Send mark before audio
                                        await ws.send_json({
                                            "event": "mark",
                                            "mark": {"name": "startResponse"}
                                        })
                                        
                                        await send_audio_to_twilio(ws, speech_path)
                                        
                                        # Send mark after audio
                                        await ws.send_json({
                                            "event": "mark", 
                                            "mark": {"name": "endResponse"}
                                        })
                                        
                                        print("[CONVERSATION] 🔄 Audio sent, waiting for next input...")
                                        
                                        # Clean up speech file
                                        try:
                                            os.remove(speech_path)
                                        except:
                                            pass
                                    else:
                                        print("[TTS] ❌ Failed to generate speech file")
                                        # Send a fallback text response
                                        await ws.send_json({
                                            "event": "mark",
                                            "mark": {"name": "error", "data": "Could not generate audio response"}
                                        })
                                else:
                                    print("[WEBSOCKET] Connection lost, skipping audio response")
                                    conversation_active = False
                            else:
                                print("[STT] ⚠️ No transcript or empty transcript received")
                                
                        except asyncio.TimeoutError:
                            print("[ERROR] ⏱️ Processing timeout - skipping this audio chunk")
                        except Exception as process_err:
                            print(f"[ERROR] ❌ Audio processing failed: {process_err}")
                            
                    except Exception as audio_err:
                        print(f"[ERROR] ❌ Audio file creation failed: {audio_err}")
                        
                elif not websocket_is_open(ws):
                    print("[WEBSOCKET] Connection lost, ending conversation")
                    conversation_active = False
                else:
                    print(f"[AUDIO] ⚠️ Insufficient audio data: {len(pcm_frames)} bytes")
                
            except Exception as loop_err:
                print(f"[ERROR] ❌ Error in conversation loop: {loop_err}")
                conversation_active = False
                
            finally:
                # Clean up temp file
                if temp_audio_file and os.path.exists(temp_audio_file):
                    try:
                        os.remove(temp_audio_file)
                    except:
                        pass
                
    except WebSocketDisconnect:
        print("[WEBSOCKET] Client disconnected gracefully")
    except Exception as e:
        import traceback
        print(f"[WEBSOCKET ERROR] {e}")
        traceback.print_exc()
    finally:
        print("[WEBSOCKET] 🔌 Cleaning up and closing connection")
        try:
            if websocket_is_open(ws):
                await ws.close()
        except:
            pass