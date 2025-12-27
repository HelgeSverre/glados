import { Database } from 'bun:sqlite';
import { mkdirSync } from 'fs';
import type { AudioEntry } from './types';

const DB_PATH = './data/glados-voice.db';

// Ensure data directory exists
try {
  mkdirSync('./data', { recursive: true });
} catch {
  // Directory already exists
}

const db = new Database(DB_PATH);

// Enable WAL mode and set busy timeout for concurrent access with Python worker
db.exec('PRAGMA journal_mode = WAL');
db.exec('PRAGMA busy_timeout = 5000');

// Initialize schema
db.exec(`
  CREATE TABLE IF NOT EXISTS audio_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'success', 'error')),
    error_message TEXT,
    audio_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER
  );
  CREATE INDEX IF NOT EXISTS idx_status_created ON audio_entries(status, created_at);
`);

// Prepared statements for performance
const insertStmt = db.prepare<AudioEntry, [string]>(
  'INSERT INTO audio_entries (text) VALUES (?) RETURNING *'
);

const selectAllStmt = db.prepare<AudioEntry, []>(
  'SELECT * FROM audio_entries ORDER BY id DESC'
);

const selectOneStmt = db.prepare<AudioEntry, [number]>(
  'SELECT * FROM audio_entries WHERE id = ?'
);

export function createEntry(text: string): AudioEntry {
  return insertStmt.get(text) as AudioEntry;
}

export function getAllEntries(): AudioEntry[] {
  return selectAllStmt.all() as AudioEntry[];
}

export function getEntry(id: number): AudioEntry | null {
  return selectOneStmt.get(id) as AudioEntry | null;
}

export { db };
