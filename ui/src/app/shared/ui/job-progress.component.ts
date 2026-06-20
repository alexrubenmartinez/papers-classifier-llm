import { Component, DestroyRef, OnInit, computed, effect, inject, input, output, signal } from '@angular/core';
import { JobStatus } from '../../core/models';
import { SseHandle, SseService } from '../../core/sse/sse.service';

@Component({
  standalone: true,
  selector: 'app-job-progress',
  template: `
    @if (state(); as job) {
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full inline-block {{ statusDot(job.status) }}"
                  [class.animate-pulse]="job.status === 'running' || job.status === 'queued'"></span>
            <span class="font-mono text-[11px] uppercase tracking-wider text-ink-2">{{ job.type || 'job' }}</span>
            <span class="font-mono text-[11px] text-ink-3">· {{ job.status }}</span>
          </div>
          @if (job.total) {
            <span class="font-mono text-[11px] tabular-nums text-ink-3">{{ job.processed ?? 0 }}/{{ job.total }}</span>
          }
        </div>

        @if (job.total && job.processed != null) {
          <div class="h-1.5 rounded-full bg-paper-2 overflow-hidden">
            <div class="h-full bg-jade transition-all duration-500 ease-spring"
                 [style.width.%]="(job.processed / job.total) * 100"></div>
          </div>
        }

        <p class="font-mono text-[11px] text-ink-2">
          <span class="text-ink-3">stage:</span> {{ job.stage }}
        </p>

        @if (job.error) {
          <p class="font-mono text-[11px] text-ember">{{ job.error }}</p>
        }
      </div>
    } @else {
      <p class="font-mono text-[11px] text-ink-3">Conectando…</p>
    }
  `,
})
export class JobProgressComponent implements OnInit {
  private sse = inject(SseService);
  private destroyRef = inject(DestroyRef);
  jobId = input.required<string>();

  // El handle se setea en ngOnInit (no en constructor) porque `jobId()` aun no
  // existe en el momento de construccion. Usamos un signal para que `state` lo
  // observe reactivamente y se actualice cuando llega.
  private handle = signal<SseHandle<JobStatus> | null>(null);
  state = computed<JobStatus | null>(() => this.handle()?.state() ?? null);

  /** Emite cada actualizacion del SSE. El padre puede sincronizar su snapshot local. */
  statusChange = output<JobStatus>();

  constructor() {
    effect(() => {
      const s = this.state();
      if (s) this.statusChange.emit(s);
    });
  }

  ngOnInit() {
    const h = this.sse.streamJob(this.jobId());
    this.handle.set(h);
    this.destroyRef.onDestroy(() => h.close());
  }

  statusDot(status: JobStatus['status']): string {
    if (status === 'completed') return 'bg-jade';
    if (status === 'failed') return 'bg-ember';
    if (status === 'running' || status === 'queued') return 'bg-jade';
    return 'bg-ink-3';
  }
}
