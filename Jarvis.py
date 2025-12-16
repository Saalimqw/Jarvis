import os
import sys
import webbrowser
import subprocess
import speech_recognition as sr
import pyttsx3
import json
import threading
from groq import Groq

# ================= CONFIG =================

GROQ_API_KEY = "your_groq_api_key_here"
WAKE_WORD = "jarvis"
MODEL_NAME = "The_model_you_used_while_making_the_api_key_put_that_model_name_here"
INITIAL_ENERGY_THRESHOLD = 200
AMBIENT_NOISE_DURATION = 1.0

# =========================================

# ---- GLOBAL STATE ----
is_speaking = False
tts_lock = threading.Lock()

# ---- GROQ CLIENT ----
client = Groq(api_key=GROQ_API_KEY)

# ---- SPEECH ENGINES ----
r = sr.Recognizer()
r.energy_threshold = INITIAL_ENERGY_THRESHOLD
mic = sr.Microphone()
tts_engine = pyttsx3.init()

# ----------------------------------------
# TTS (INTERRUPTIBLE, THREADED)
# ----------------------------------------

def tts_worker(text):
    global is_speaking
    with tts_lock:
        is_speaking = True
        tts_engine.say(text)
        tts_engine.runAndWait()
        is_speaking = False

def speak_interruptible(text):
    global is_speaking
    if is_speaking:
        tts_engine.stop()
        is_speaking = False

    print(f"JARVIS: {text}")
    threading.Thread(
        target=tts_worker,
        args=(text,),
        daemon=True
    ).start()

def stop_speaking():
    global is_speaking
    if is_speaking:
        tts_engine.stop()
        is_speaking = False
        print("JARVIS: Speech stopped.")

# ----------------------------------------
# LISTENING
# ----------------------------------------

def listen_for_command():
    with mic as source:
        try:
            if not is_speaking:
                r.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_DURATION)

            audio = r.listen(
                source,
                timeout=2 if is_speaking else 5,
                phrase_time_limit=3
            )
            return r.recognize_google(audio).lower()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            return "request_error"

# ----------------------------------------
# GROQ COMMAND PROCESSING
# ----------------------------------------

def process_command(text):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "open_website",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_program",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "program_name": {"type": "string"}
                    },
                    "required": ["program_name"]
                }
            }
        }
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.0,
        tools=tools,
        tool_choice="auto",
        messages=[
            {"role": "system", "content": "You are JARVIS, a fast system assistant."},
            {"role": "user", "content": text}
        ]
    )

    msg = response.choices[0].message

    if msg.tool_calls:
        tool = msg.tool_calls[0]
        args = json.loads(tool.function.arguments)

        if tool.function.name == "open_website":
            return "open_website", args["url"]

        if tool.function.name == "run_program":
            return "run_program", args["program_name"]

    return "response", msg.content

# ----------------------------------------
# MAIN LOOP
# ----------------------------------------

def main():
    speak_interruptible(f"System ready. Say {WAKE_WORD}.")

    while True:
        command = listen_for_command()

        if not command:
            continue

        # INTERRUPT WHILE SPEAKING
        if is_speaking and WAKE_WORD in command and any(
            w in command for w in ["stop", "quiet", "wait", "shut"]
        ):
            stop_speaking()
            speak_interruptible("Yes?")
            continue

        if command == "request_error":
            speak_interruptible("Speech service error.")
            continue

        if WAKE_WORD not in command:
            continue

        clean = command.replace(WAKE_WORD, "").strip()

        if not clean:
            speak_interruptible("Yes?")
            continue

        if any(w in clean for w in ["exit", "shutdown", "bye"]):
            speak_interruptible("Shutting down.")
            break

        speak_interruptible("Processing.")
        action, value = process_command(clean)

        if action == "open_website":
            if not value.startswith("http"):
                value = "https://" + value
            speak_interruptible(f"Opening {value}")
            webbrowser.open_new_tab(value)

        elif action == "run_program":
            speak_interruptible(f"Launching {value}")
            subprocess.Popen(value, shell=True)

        elif action == "response":
            speak_interruptible(value)

if __name__ == "__main__":
    main()

