export interface AudioEntry {
  id: number;
  text: string;
  status: 'pending' | 'processing' | 'success' | 'error';
  error_message: string | null;
  audio_path: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
}
