import torch
import sys
import os
import warnings
import threading
import time
import argparse
import wave
import subprocess
import random
import json

# Suppress PyTorch nested tensor warning from pre-compiled models
warnings.filterwarnings("ignore", message="enable_nested_tensor is True")

# Change to the glados-tts directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Patch torch.load to use weights_only=False for compatibility with older models
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from utils.tools import prepare_text
from scipy.io.wavfile import write

# Constants
OUTPUT_PATH = '/Users/helge/code/glados/glados-tts/output.wav'
GLADOS_SYSTEM_PROMPT = "You are GLaDOS from Portal. Respond in character: sardonic, passive-aggressive, darkly humorous. Keep responses brief (1-3 sentences). Never break character."

SPINNER_MESSAGES = {
    'thinking': [
        "Aperture Science Testing Protocol...",
        "Consulting the mainframe...",
        "Processing your insignificant query...",
        "Calculating optimal sarcasm levels...",
    ],
    'generating': [
        "Synthesizing vocal patterns...",
        "Warming up the neurotoxin-- voice module...",
        "Preparing test results...",
        "Generating audio for science...",
        "The cake is being prepared...",
    ]
}

# Global model references (lazy loaded)
_models = None

def get_models():
    """Lazy load models on first use."""
    global _models
    if _models is None:
        # Load embedding for Portal 2 voice
        emb = torch.load('models/emb/glados_p2.pt')

        # Select device
        if torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'

        # Load models
        glados = torch.jit.load('models/glados-new.pt')
        vocoder = torch.jit.load('models/vocoder-gpu.pt', map_location=device)

        # Warm up
        for i in range(2):
            init = glados.generate_jit(prepare_text(str(i)), emb, 1.0)
            init_mel = init['mel_post'].to(device)
            init_vo = vocoder(init_mel)

        _models = {'emb': emb, 'device': device, 'glados': glados, 'vocoder': vocoder}
    return _models

def spinner(stop_event, phase='thinking'):
    """Display animated spinner with on-brand messages."""
    frames = ['◐', '◓', '◑', '◒']
    message = random.choice(SPINNER_MESSAGES[phase])
    i = 0
    while not stop_event.is_set():
        print(f"\r\033[38;5;208m{frames[i]} {message}\033[0m", end='', flush=True)
        i = (i + 1) % 4
        time.sleep(0.2)
    print("\r\033[K", end='', flush=True)

def get_ai_response(prompt):
    """Get response from Claude with spinner."""
    stop_spinner = threading.Event()
    spin_thread = threading.Thread(target=spinner, args=(stop_spinner, 'thinking'))
    spin_thread.start()

    result = subprocess.run([
        'claude', '-p', prompt,
        '--system-prompt', GLADOS_SYSTEM_PROMPT,
        '--allowedTools', 'WebSearch', 'WebFetch'
    ], capture_output=True, text=True)

    stop_spinner.set()
    spin_thread.join()
    return result.stdout.strip()

def get_ai_response_with_session(prompt, session_id=None):
    """Get Claude response with session management, returns (text, session_id)."""
    cmd = [
        'claude', '-p', prompt,
        '--system-prompt', GLADOS_SYSTEM_PROMPT,
        '--allowedTools', 'WebSearch', 'WebFetch',
        '--output-format', 'json'
    ]

    if session_id:
        cmd.extend(['--resume', session_id])

    result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        data = json.loads(result.stdout)
        # Extract response text from result field
        text = data['result']
        new_session_id = data['session_id']
        return text, new_session_id
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # Fallback if JSON parsing fails
        return result.stdout.strip() or f"Error: {result.stderr}", None

def generate_tts(text):
    """Generate TTS audio from text, returns audio array."""
    models = get_models()
    x = prepare_text(text)

    with torch.no_grad():
        tts_output = models['glados'].generate_jit(x, models['emb'], 1.0)
        mel = tts_output['mel_post'].to(models['device'])
        audio = models['vocoder'](mel)
        audio = audio.squeeze()
        audio = audio * 32768.0
        audio = audio.cpu().numpy().astype('int16')

    return audio

def generate_audio_with_spinner(text, output_path):
    """Generate TTS audio with spinner display."""
    stop_spinner = threading.Event()
    spin_thread = threading.Thread(target=spinner, args=(stop_spinner, 'generating'))
    spin_thread.start()

    audio = generate_tts(text)
    write(output_path, 22050, audio)

    stop_spinner.set()
    spin_thread.join()

def typewriter(text, duration):
    """Print text with typewriter effect, slightly faster than audio."""
    # Calculate delay per character to finish before audio ends (1.15x faster)
    char_delay = (duration / 1.15) / len(text) if text else 0.05
    # Clamp to reasonable range
    char_delay = max(0.02, min(char_delay, 0.15))

    print("\033[38;5;208mGLaDOS:\033[0m ", end='', flush=True)
    for char in text:
        print(char, end='', flush=True)
        time.sleep(char_delay)
    print()

def play_and_type(audio_path, text):
    """Play audio while typing out text simultaneously."""
    # Get audio duration
    with wave.open(audio_path, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate

    # Start audio in background
    audio_proc = subprocess.Popen(['afplay', audio_path])

    # Type while audio plays
    typewriter(text, duration)

    # Wait for audio to finish
    audio_proc.wait()

def speak_mode(text):
    """Full AI conversation mode with spinners and typewriter."""
    response = get_ai_response(text)
    generate_audio_with_spinner(response, OUTPUT_PATH)
    play_and_type(OUTPUT_PATH, response)

def say_mode(text, play_audio=True):
    """Direct TTS mode - just speak the provided text."""
    print("Initializing GLaDOS TTS Engine...")
    models = get_models()
    print(f"Using device: {models['device']}")
    print("Models loaded. Generating speech...")

    audio = generate_tts(text)
    write(OUTPUT_PATH, 22050, audio)
    print(f"Audio saved to {OUTPUT_PATH}")

    if play_audio:
        subprocess.run(['afplay', OUTPUT_PATH])

def main():
    parser = argparse.ArgumentParser(description='GLaDOS TTS Engine')
    parser.add_argument('text', nargs='?', default=None, help='Text to speak')
    parser.add_argument('--ai', action='store_true', help='AI conversation mode with Claude')
    parser.add_argument('--no-play', action='store_true', help='Generate audio without playing')
    args = parser.parse_args()

    # Handle text input: prefer args, then stdin, then default
    if args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        text = "Installation complete. The Enrichment Center reminds you that the weighted companion cube will never threaten to stab you."

    if args.ai:
        speak_mode(text)
    else:
        say_mode(text, play_audio=not args.no_play)

if __name__ == '__main__':
    main()
