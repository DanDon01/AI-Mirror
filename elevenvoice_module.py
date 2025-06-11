import os
import openai
import sounddevice as sd
import soundfile as sf
import requests
import speech_recognition as sr
import tempfile
from datetime import datetime

# --------------- CONFIG ----------------
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "your-eleven-api-key")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "your-voice-id")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-api-key")
USE_GPT_4O = True  # Toggle between GPT-4o and GPT-3.5
# ---------------------------------------

LOGFILE = "mirror_voice_log.txt"

def log_interaction(heard, replied):
    with open(LOGFILE, "a") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] Heard: {heard}\n")
        f.write(f"[{timestamp}] Replied: {replied}\n\n")

class ElevenVoice:
    """
    ElevenLabs-based voice interaction module for AI Mirror.
    Provides speech-to-text, text generation, and text-to-speech capabilities.
    """

    def __init__(self):
        openai.api_key = OPENAI_API_KEY
        self.recogniser = sr.Recognizer()
        self.microphone = sr.Microphone()

    def listen(self):
        """
        Listen to user input and convert speech to text.
        Returns: str: Transcribed text from user speech
        """
        with self.microphone as source:
            print("[🎙️] Listening...")
            self.recogniser.adjust_for_ambient_noise(source)
            audio = self.recogniser.listen(source)
        print("[🧠] Transcribing...")
        try:
            return self.recogniser.recognize_google(audio)
        except sr.UnknownValueError:
            return "Sorry, I didn't catch that."
        except sr.RequestError:
            return "Speech recognition service failed."

    def generate_response(self, prompt):
        """
        Generate AI response using OpenAI's GPT models.
        Args:
            prompt (str): User input to generate response for
        Returns:
            str: Generated AI response
        """
        print("[🤖] Thinking...")
        model = "gpt-4o" if USE_GPT_4O else "gpt-3.5-turbo"
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are MirrorVoice, a friendly but occasionally sarcastic hallway mirror."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[❌] Error generating response: {e}")
            return "Sorry, I'm having trouble thinking right now."

    def speak(self, text):
        """
        Convert text to speech using ElevenLabs API and play it.
        Args:
            text (str): Text to be converted to speech
        """
        print(f"[🗣️] Speaking: {text}")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
        headers = {
            "Accept": "audio/mpeg",
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.7,
                "similarity_boost": 0.8
            }
        }

        with requests.post(url, headers=headers, json=payload, stream=True) as r:
            if r.status_code != 200:
                print("[❌] Failed to get audio from ElevenLabs")
                return
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                for chunk in r.iter_content(chunk_size=4096):
                    temp_audio.write(chunk)
                temp_audio_path = temp_audio.name

        data, fs = sf.read(temp_audio_path, dtype='float32')
        sd.play(data, fs)
        sd.wait()

    def interact(self):
        query = self.listen()
        print(f"[🧏‍♂️] You said: {query}")
        response = self.generate_response(query)
        print(f"[💬] MirrorVoice: {response}")
        log_interaction(query, response)
        self.speak(response)

