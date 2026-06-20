/**
 * Mirror de los schemas Pydantic de examen-api (app/schemas.py).
 * Cualquier cambio del backend que toque la API pública debe reflejarse aquí.
 */

export interface ScoreBreakdown {
  keyword: number;
  tfidf: number;
  sbert: number;
  weighted: number;
}

export interface PaperSummary {
  paper_id: string;
  title: string;
  year: number;
  score_final: number; // 0..5
  decision: string;
}

export interface Paper extends PaperSummary {
  abstract?: string | null;
  score_breakdown: ScoreBreakdown;
  justification?: string | null;
  created_at: string;
}

export type JobStatusValue = 'queued' | 'running' | 'completed' | 'failed';

export interface JobStatus {
  job_id: string;
  paper_id: string;
  status: JobStatusValue;
  stage: string;
  filename?: string | null;
  created_at: string;
  updated_at: string;
  error?: string | null;
  type?: string | null; // 'ingest' | 'reclassify_all' | 'justify_batch'
  total?: number | null;
  processed?: number | null;
}

export interface UploadResponse {
  job_id: string;
  paper_id: string;
  status: JobStatusValue;
  stream_url: string;
}

export interface ReclassifyResponse {
  job_id: string;
  type: 'reclassify_all';
  total: number;
  stream_url: string;
}

export interface QueryConfig {
  topic_name: string;
  query_text: string;
  axes: Record<string, string[]>;
  weights: Record<string, number>;
  year_range: [number, number];
  thresholds?: Record<string, number> | null;
  updated_at?: string | null;
}

export type QueryConfigUpdate = Partial<QueryConfig>;

export interface JustifyRequest {
  paper_ids?: string[];
  top?: number;
  min_score?: number;
}

export interface JustifyResponse {
  paper_id: string;
  justification: string;
  generated_in_ms: number;
}

export interface JustifyBatchResponse {
  job_id: string;
  type: 'justify_batch';
  total: number;
  stream_url: string;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  model?: string;
  messages: ChatMessage[];
}

export interface ChatResponse {
  model: string;
  message: string;
  total_duration_ms: number;
  eval_count: number;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  papers: number;
  jobs_in_flight: number;
  sbert_loaded: boolean;
  tfidf_fitted: boolean;
}

// ---------------------------------------------------------------------------
// Helpers de tier (Bronze/Silver/Gold)
// ---------------------------------------------------------------------------

export type Tier = 'gold' | 'silver' | 'bronze' | 'out_of_range';

export function scoreToTier(score: number): Tier {
  if (score === 0) return 'out_of_range';
  if (score >= 4) return 'gold';
  if (score === 3) return 'silver';
  return 'bronze';
}

export const TIER_LABEL: Record<Tier, string> = {
  gold: 'Gold',
  silver: 'Silver',
  bronze: 'Bronze',
  out_of_range: 'Fuera de rango',
};
