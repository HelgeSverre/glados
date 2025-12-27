import asyncio
import aiohttp
from aiohttp import web
import json
import random
import wave
import sys
import os
import logging
from uuid import uuid4

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('glados')

# Add parent dir to path for glados import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Change to glados directory for model loading
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glados import get_ai_response_with_session, generate_tts, SPINNER_MESSAGES, get_models
from scipy.io.wavfile import write

AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

# Pre-load models on startup
log.info("Pre-loading GLaDOS TTS models...")
get_models()
log.info("Models loaded. Server ready.")


async def safe_send(ws, data, client_id="?"):
    """Send JSON only if connection is open."""
    if ws.closed:
        log.warning(f"[{client_id}] Cannot send - connection closed")
        return False
    try:
        await ws.send_json(data)
        return True
    except Exception as e:
        log.warning(f"[{client_id}] Failed to send: {e}")
        return False


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_id = uuid4().hex[:8]
    log.info(f"[{client_id}] Client connected")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    prompt = data.get('prompt', '')
                    session_id = data.get('session_id')

                    if not prompt:
                        await safe_send(ws, {'type': 'error', 'message': 'No prompt provided'}, client_id)
                        continue

                    log.info(f"[{client_id}] Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
                    if session_id:
                        log.info(f"[{client_id}] Resuming session: {session_id}")

                    # Phase 1: Thinking
                    thinking_msg = random.choice(SPINNER_MESSAGES['thinking'])
                    log.info(f"[{client_id}] Phase: {thinking_msg}")
                    if not await safe_send(ws, {
                        'type': 'status',
                        'phase': 'thinking',
                        'message': thinking_msg
                    }, client_id):
                        continue

                    # Get AI response (runs in thread pool to not block)
                    loop = asyncio.get_event_loop()
                    text, new_session_id = await loop.run_in_executor(
                        None, get_ai_response_with_session, prompt, session_id
                    )

                    log.info(f"[{client_id}] Claude response: {text[:100]}{'...' if len(text) > 100 else ''}")
                    log.info(f"[{client_id}] Session ID: {new_session_id}")

                    if not text:
                        await safe_send(ws, {'type': 'error', 'message': 'Failed to get AI response'}, client_id)
                        continue

                    # Phase 2: Generating audio
                    generating_msg = random.choice(SPINNER_MESSAGES['generating'])
                    log.info(f"[{client_id}] Phase: {generating_msg}")
                    if not await safe_send(ws, {
                        'type': 'status',
                        'phase': 'generating',
                        'message': generating_msg
                    }, client_id):
                        continue

                    audio = await loop.run_in_executor(None, generate_tts, text)
                    audio_filename = f"output_{uuid4().hex[:8]}.wav"
                    audio_path = os.path.join(AUDIO_DIR, audio_filename)
                    write(audio_path, 22050, audio)

                    # Get audio duration
                    with wave.open(audio_path, 'rb') as wf:
                        duration = wf.getnframes() / wf.getframerate()

                    log.info(f"[{client_id}] Audio generated: {audio_filename} ({duration:.1f}s)")

                    # Phase 3: Complete
                    await safe_send(ws, {
                        'type': 'response',
                        'text': text,
                        'session_id': new_session_id,
                        'audio_url': f'/audio/{audio_filename}',
                        'audio_duration': duration
                    }, client_id)

                except json.JSONDecodeError as e:
                    log.error(f"[{client_id}] Invalid JSON: {e}")
                    await safe_send(ws, {'type': 'error', 'message': 'Invalid JSON'}, client_id)
                except Exception as e:
                    log.error(f"[{client_id}] Error handling message: {e}")
                    await safe_send(ws, {'type': 'error', 'message': str(e)}, client_id)

            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.error(f"[{client_id}] WebSocket error: {ws.exception()}")

    except asyncio.CancelledError:
        log.info(f"[{client_id}] Connection cancelled")
    except Exception as e:
        log.error(f"[{client_id}] Unexpected error: {e}")
    finally:
        log.info(f"[{client_id}] Client disconnected")

    return ws


async def index_handler(request):
    """Serve index.html for root path."""
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'index.html'))


async def on_shutdown(app):
    log.info("Shutting down server...")


app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_get('/', index_handler)
app.router.add_get('/ws', websocket_handler)
app.router.add_static('/audio', AUDIO_DIR)

if __name__ == '__main__':
    log.info("Starting GLaDOS Web Server on http://localhost:8765")
    try:
        web.run_app(app, host='localhost', port=8765, print=None)
    except KeyboardInterrupt:
        log.info("Server stopped by user")
