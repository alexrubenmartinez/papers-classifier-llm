import { Injectable, Signal, signal } from '@angular/core';
import { JobStatus } from '../models';
import { API_BASE } from '../api/api.config';

export interface SseHandle<T> {
  state: Signal<T | null>;
  close: () => void;
}

/**
 * Wrapper de EventSource a signals. Devuelve un handle con `state` (signal readonly)
 * y `close` (cleanup). El caller es responsable de invocar `close()` en su destrucción
 * (típicamente con `inject(DestroyRef).onDestroy(...)` o `effect` con `onCleanup`).
 */
@Injectable({ providedIn: 'root' })
export class SseService {
  streamJob(jobId: string): SseHandle<JobStatus> {
    const state = signal<JobStatus | null>(null);
    const source = new EventSource(`${API_BASE}/stream?job_id=${jobId}`);

    const parse = (e: MessageEvent) => {
      try { state.set(JSON.parse(e.data) as JobStatus); } catch {}
    };

    source.addEventListener('job.progress', parse as EventListener);
    source.addEventListener('job.completed', (e: MessageEvent) => {
      parse(e);
      source.close();
    });
    source.addEventListener('job.failed', (e: MessageEvent) => {
      parse(e);
      source.close();
    });

    return { state: state.asReadonly(), close: () => source.close() };
  }

  streamHeartbeat(): SseHandle<{ time: string; jobs_in_flight: number }> {
    const state = signal<{ time: string; jobs_in_flight: number } | null>(null);
    const source = new EventSource(`${API_BASE}/stream`);
    source.addEventListener('heartbeat', (e: MessageEvent) => {
      try { state.set(JSON.parse(e.data)); } catch {}
    });
    return { state: state.asReadonly(), close: () => source.close() };
  }
}
