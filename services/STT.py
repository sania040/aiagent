import os
import openai
from dotenv import load_dotenv
import numpy as np
import pyaudio
import wave
import time

class SpeechToText:
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv("OPENAI_API_KEY")
        print("[STT] Initialized SpeechToText class.")

    def transcribe_audio(self, audio_file_path):
        """Transcribes audio file to text using OpenAI's Whisper model"""
        print(f"[STT] Starting transcription for: {audio_file_path}")
        
        # Check if file exists and has content
        if not os.path.exists(audio_file_path):
            print(f"[STT] Audio file not found: {audio_file_path}")
            return None
            
        file_size = os.path.getsize(audio_file_path)
        if file_size < 1000:  # Less than 1KB
            print(f"[STT] Audio file too small: {file_size} bytes")
            return None
            
        try:
            with open(audio_file_path, "rb") as audio_file:
                print("[STT] Audio file opened, sending to OpenAI Whisper API...")
                
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"  # Specify language for better accuracy
                )
                print(f"[STT] Raw transcript response: {transcript}")
                
            # Always use .text for the result
            if hasattr(transcript, "text") and transcript.text.strip():
                result = transcript.text.strip()
                print(f"[STT] Transcription successful: '{result}'")
                return result
            else:
                print("[STT] Empty transcription result.")
                return None
                
        except Exception as e:
            print(f"[STT] Error transcribing audio: {e}")
            return None

    def record_audio(self, filename="recording.wav", silence_threshold=500, silence_duration=1.0, max_record_time=15):
        """
        Records audio from the microphone until silence is detected.
        Stops recording if silence is detected for `silence_duration` seconds,
        or if `max_record_time` is reached.
        """
        print("[STT] Starting voice-activated audio recording...")
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        print("[STT] Recording... Speak now.")
        frames = []
        silent_chunks = 0
        silence_chunk_limit = int(silence_duration * RATE / CHUNK)
        start_time = time.time()

        while True:
            data = stream.read(CHUNK)
            frames.append(data)
            audio_data = np.frombuffer(data, dtype=np.int16)
            volume = np.abs(audio_data).mean()

            if volume < silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            # Stop if silence detected for required duration or max time reached
            if silent_chunks > silence_chunk_limit:
                print("[STT] Silence detected, stopping recording.")
                break
            if time.time() - start_time > max_record_time:
                print("[STT] Max record time reached, stopping recording.")
                break

        stream.stop_stream()
        stream.close()
        p.terminate()

        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()

        print(f"[STT] Audio saved to {filename}")
        return filename