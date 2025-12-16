import os
import sys
import webbrowser
import subprocess
import speech_recognition as sr
import pyttsx3
import json
import threading # 1. NEW: For running TTS in a non-blocking way
from groq import Groq

# --- CONFIGURATION & TUNING ---
GROQ_API_KEY = "add_your_groq_api_key_here" # Using your provided key
WAKE_WORD = "jarvis"
MODEL_NAME = "add_the_model_you_select_while_generating_the_api_key_here"

# MICROPHONE TUNING
INITIAL_ENERGY_THRESHOLD = 200
AMBIENT_NOISE_DURATION = 1.0

# 2. NEW GLOBAL FLAG for managing speech state
is_speaking = False

# Initialize the Groq Client (using your existing code)
try:
    if GROQ_API_KEY == "YOUR_GROQ_API_KEY":
        print("ERROR: Please replace 'YOUR_GROQ_API_KEY' with your actual key in the configuration block.")
        sys.exit(1)
        
    client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    sys.exit(1)

# Initialize the speech recognition and TTS engines
r = sr.Recognizer()
r.energy_threshold = INITIAL_ENERGY_THRESHOLD
mic = sr.Microphone()
tts_engine = pyttsx3.init()

# === TEMPORARY CODE TO FIND MIC INDEX ===
# (Retained for setup convenience)
print("Available Microphones:")
for index, name in enumerate(sr.Microphone.list_microphone_names()):
    print(f"Index {index}: {name}")
# ========================================

# ------------------------------------
# 1. SPEECH FUNCTIONS
# ------------------------------------

def stop_speaking():
    """Immediately stops the pyttsx3 engine."""
    global is_speaking
    try:
        if is_speaking:
            tts_engine.stop()
            is_speaking = False
            print("JARVIS: Speech interrupted.")
            return True
    except Exception as e:
        print(f"Error stopping TTS engine: {e}")
    return False


def set_is_speaking_done(name, completed):
    """Callback function to reset the speaking flag when speech is done."""
    global is_speaking
    is_speaking = False
    # You can optionally start listening again here if needed, but we'll let the main loop handle it.


# Attach the callback function
tts_engine.connect('finished-utterance', set_is_speaking_done)


def speak_interruptible(text, recognizer_instance):
    """
    Converts text to speech using a flag to track state.
    It temporarily ignores mic input during non-interruptible speech.
    """
    global is_speaking
    
    # Store the original threshold
    original_threshold = recognizer_instance.energy_threshold
    
    # Temporarily raise the threshold significantly high to ignore TTS output
    recognizer_instance.energy_threshold = 4000
    
    print(f"JARVIS: {text}")
    is_speaking = True
    
    # The say() call is non-blocking, but tts_engine.runAndWait() is.
    # We use tts_engine.startLoop() and tts_engine.endLoop() with event handling
    # to achieve the interruptible behavior.
    tts_engine.say(text)
    
    # You must call startLoop() or runAndWait() to process the queue.
    # To keep the main loop reactive, we only call startLoop() if not already running
    # and rely on the internal event loop to process the speech and call the 'finished-utterance' event.
    try:
        tts_engine.runAndWait() 
    except RuntimeError:
        # This catches the error if runAndWait() is called on an engine that is already running.
        # In a simple non-threaded setup, runAndWait() is necessary to execute the speech.
        pass

    # Restore the original threshold
    recognizer_instance.energy_threshold = original_threshold
    # The is_speaking flag is reset by the callback `set_is_speaking_done` now.


def listen_for_command():
    # ... (Keep your existing listen_for_command function)
    """Listens for user speech and returns the transcribed text."""
    with mic as source:
        # Check if the engine is speaking. If so, we can try to listen
        # at a slightly higher sensitivity to catch the interrupt command.
        if is_speaking:
            print("LISTENING FOR INTERRUPT...")
            # Set a shorter timeout for interruption attempts
            timeout_val = 2
        else:
            print(f"Listening for '{WAKE_WORD}'...")
            timeout_val = 5
            # Use the tuned duration for better calibration when not speaking
            r.adjust_for_ambient_noise(source, duration=AMBIENT_NOISE_DURATION)

        try:
            audio = r.listen(source, timeout=timeout_val, phrase_time_limit=5) # Reduced phrase limit for quicker catch
            text = r.recognize_google(audio).lower()
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            # We don't want to spam the user with 'unknown value' during quiet moments
            return "unknown_value"
        except sr.RequestError:
            return "request_error"

# ------------------------------------
# 2. GROQ API AND COMMAND EXECUTION LOGIC (No change needed here)
# ------------------------------------

def process_command(text):
    # (Keep your existing process_command function exactly as it is)
    # Define the available tools (functions) for the model to choose from
    tools = [
        {
            "type": "function",
            "function": {
                "name": "open_website",
                "description": "Opens a specified website or URL in the default web browser. Use this for requests like 'open YouTube' or 'go to Google Maps'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL of the website to open, e.g., 'https://www.youtube.com'."
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_program",
                "description": "Executes a common local application or program on the user's operating system (like calculator, notepad, command prompt).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "program_name": {
                            "type": "string",
                            "description": "The executable name or command to run, e.g., 'calc', 'notepad', 'explorer'."
                        }
                    },
                    "required": ["program_name"]
                }
            }
        }
    ]

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"You are JARVIS, a helpful, high-speed AI assistant. Use the provided tools to execute system actions. For general questions, provide a concise answer directly. The current model is {MODEL_NAME}."},
                {"role": "user", "content": text}
            ],
            model=MODEL_NAME,
            tools=tools,
            tool_choice="auto",
            temperature=0.0
        )
        
        response_message = chat_completion.choices[0].message
        
        # --- EXECUTE TOOL CALL ---
        if response_message.tool_calls:
            tool_call = response_message.tool_calls[0]
            function_name = tool_call.function.name
            
            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                return "error", "The model returned malformed tool arguments."

            if function_name == "open_website":
                url = function_args.get("url", "https://www.google.com")
                return "open_website", url
            
            elif function_name == "run_program":
                program_name = function_args.get("program_name")
                return "run_program", program_name
            
            return "response", f"The model requested an unknown tool: {function_name}"


        # --- RETURN TEXT RESPONSE ---
        return "response", response_message.content

    except Exception as e:
        error_message = str(e)
        if "Authentication" in error_message or "401" in error_message:
            return "error", "Authentication failed. Please check your Groq API key."
        return "error", f"An unexpected Groq API error occurred: {error_message}"

# ------------------------------------
# 3. MAIN LOOP
# ------------------------------------

def main():
    speak_interruptible(f"System ready. Listening for the activation word: {WAKE_WORD}.", r)

    try:
        while True:
            # 3. NEW: Check if JARVIS is currently speaking before listening
            if is_speaking:
                # If speaking, we still listen, but only for the interrupt command
                command = listen_for_command()
                
                # Check for the interrupt command *before* processing it generally
                if WAKE_WORD in command and ("stop" in command or "shut up" in command or "quiet" in command):
                    stop_speaking()
                    speak_interruptible("Interrupted. What is your command?", r)
                    continue # Go back to the start of the while loop
                
                # If the speaking flag is still True, we continue to the next loop iteration
                if is_speaking:
                    # Allow the TTS engine to process its events while waiting
                    # pyttsx3.init() handles this internally, but good practice
                    continue 

            # If not speaking, listen for a full command
            command = listen_for_command()

            if command == "request_error":
                speak_interruptible("I'm having trouble connecting to the speech service. Check your connection.", r)
                continue
            
            if command == "unknown_value":
                continue
            
            if command and WAKE_WORD in command:
                clean_command = command.replace(WAKE_WORD, "").strip()
                
                if not clean_command:
                    speak_interruptible("Yes, how can I assist you?", r)
                    continue
                
                # Check for explicit shutdown command
                if "exit" in clean_command or "shutdown" in clean_command:
                    speak_interruptible("Shutting down. Goodbye.", r)
                    break
                
                speak_interruptible("Processing your request...", r)
                action, value = process_command(clean_command)

                # Execute the action
                if action == "open_website":
                    if not value.startswith(('http://', 'https://')):
                        value = 'https://' + value
                        
                    speak_interruptible(f"Attempting to open {value}.", r)
                    if not webbrowser.open_new_tab(value):
                        speak_interruptible("I was unable to launch your default web browser.", r)
                    
                elif action == "run_program":
                    try:
                        speak_interruptible(f"Launching {value}.", r)
                        subprocess.Popen(value, shell=True)
                    except FileNotFoundError:
                        speak_interruptible(f"I could not find or launch the program named {value}.", r)
                        
                elif action == "response":
                    speak_interruptible(value, r)
                    
                elif action == "error":
                    speak_interruptible(value, r)
    
    except KeyboardInterrupt:
        stop_speaking() # Ensure speech is stopped on interrupt
        speak_interruptible("Program interrupted. Shutting down.", r)
        sys.exit(0)
    except Exception as e:
        print(f"An unexpected critical error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
