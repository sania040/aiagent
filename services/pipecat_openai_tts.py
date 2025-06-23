from services.TTS import TextToSpeech

class OpenAITTSBlock:
    def __init__(self, voice="alloy"):
        self.tts = TextToSpeech()
        self.voice = voice

    def __call__(self, text):
        if text:
            return self.tts.generate_speech(text, voice=self.voice)
        return None