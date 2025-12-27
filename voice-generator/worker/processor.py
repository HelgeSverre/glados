#!/usr/bin/env python3
"""
GLaDOS Voice Generator - Background TTS Processor

Polls SQLite database for pending entries and generates audio using
the existing GLaDOS TTS engine.
"""

import sqlite3
import sys
import os
import time
import wave
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('glados-worker')

# Path configuration
WORKER_DIR = Path(__file__).parent.absolute()
VOICE_GEN_DIR = WORKER_DIR.parent
GLADOS_ROOT = VOICE_GEN_DIR.parent
DB_PATH = VOICE_GEN_DIR / 'data' / 'glados-voice.db'
AUDIO_OUTPUT_DIR = VOICE_GEN_DIR / 'public' / 'audio'

# Ensure output directory exists
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Add glados root to path for imports
sys.path.insert(0, str(GLADOS_ROOT))
os.chdir(GLADOS_ROOT)  # Required for model loading (models are relative paths)

# Import TTS after path setup
from glados import generate_tts, get_models
from scipy.io.wavfile import write as write_wav

# Constants
POLL_INTERVAL = 2.0  # seconds between database polls
SAMPLE_RATE = 22050


def get_db_connection():
    """Create SQLite connection with WAL mode settings."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def claim_pending_entry(conn):
    """
    Atomically claim one pending entry for processing.
    Returns the entry dict or None if no pending entries.
    """
    cursor = conn.cursor()

    # Find oldest pending entry
    cursor.execute('''
        SELECT id, text FROM audio_entries
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT 1
    ''')
    row = cursor.fetchone()

    if not row:
        return None

    entry_id = row['id']

    # Atomically update to processing (prevents race conditions)
    cursor.execute('''
        UPDATE audio_entries
        SET status = 'processing', started_at = datetime('now')
        WHERE id = ? AND status = 'pending'
    ''', (entry_id,))

    if cursor.rowcount == 0:
        # Another worker claimed it
        return None

    conn.commit()
    return {'id': row['id'], 'text': row['text']}


def mark_success(conn, entry_id, audio_path, duration_ms):
    """Mark entry as successfully completed."""
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE audio_entries
        SET status = 'success',
            audio_path = ?,
            duration_ms = ?,
            completed_at = datetime('now')
        WHERE id = ?
    ''', (audio_path, duration_ms, entry_id))
    conn.commit()


def mark_error(conn, entry_id, error_message):
    """Mark entry as failed with error message."""
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE audio_entries
        SET status = 'error',
            error_message = ?,
            completed_at = datetime('now')
        WHERE id = ?
    ''', (str(error_message)[:500], entry_id))
    conn.commit()


def get_audio_duration_ms(filepath):
    """Get duration of WAV file in milliseconds."""
    with wave.open(str(filepath), 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return int((frames / rate) * 1000)


def process_entry(entry):
    """Generate TTS audio for a single entry."""
    entry_id = entry['id']
    text = entry['text']

    log.info(f"Processing entry {entry_id}: {text[:50]}{'...' if len(text) > 50 else ''}")

    # Generate audio using existing TTS
    audio = generate_tts(text)

    # Save to file
    audio_filename = f"{entry_id}.wav"
    audio_path = AUDIO_OUTPUT_DIR / audio_filename
    write_wav(str(audio_path), SAMPLE_RATE, audio)

    # Get duration
    duration_ms = get_audio_duration_ms(audio_path)

    log.info(f"Generated {audio_filename} ({duration_ms}ms)")

    # Return relative path for database (from public folder)
    return f"audio/{audio_filename}", duration_ms


def main():
    """Main worker loop."""
    log.info("=" * 50)
    log.info("GLaDOS Voice Generator Worker")
    log.info("=" * 50)
    log.info(f"Database: {DB_PATH}")
    log.info(f"Audio output: {AUDIO_OUTPUT_DIR}")

    # Check database exists
    if not DB_PATH.exists():
        log.error(f"Database not found: {DB_PATH}")
        log.error("Start the Bun server first to create the database.")
        sys.exit(1)

    # Pre-load TTS models
    log.info("Loading TTS models (this may take a moment)...")
    get_models()
    log.info("Models loaded. Worker ready.")
    log.info("Polling for new entries...")

    # Main processing loop
    while True:
        try:
            conn = get_db_connection()
            entry = claim_pending_entry(conn)

            if entry:
                try:
                    audio_path, duration_ms = process_entry(entry)
                    mark_success(conn, entry['id'], audio_path, duration_ms)
                except Exception as e:
                    log.error(f"Entry {entry['id']} failed: {e}")
                    mark_error(conn, entry['id'], str(e))
            else:
                # No pending entries, sleep before polling again
                time.sleep(POLL_INTERVAL)

            conn.close()

        except KeyboardInterrupt:
            log.info("Worker stopped by user")
            break
        except Exception as e:
            log.error(f"Worker error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
