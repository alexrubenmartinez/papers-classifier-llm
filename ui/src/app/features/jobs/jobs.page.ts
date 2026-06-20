import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { JobsService } from '../../core/api/jobs.service';
import { JobStatus } from '../../core/models';
import { JobProgressComponent } from '../../shared/ui/job-progress.component';

@Component({
  standalone: true,
  selector: 'app-jobs',
  imports: [RouterLink, JobProgressComponent],
  template: `
    <section class="space-y-6 pt-6 max-w-4xl">
      <header class="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">jobs</p>
          <h1 class="font-display text-4xl text-ink">{{ activeId() ? 'Job ' + activeId() : 'Todos los jobs' }}</h1>
        </div>
        @if (!activeId()) {
          <button (click)="refresh()" class="pill !text-[11px]">Refrescar</button>
        }
      </header>

      @if (activeId(); as id) {
        <!-- Vista detalle de un job particular -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-4">
          <p class="font-mono text-[11px] text-ink-3">job_id: {{ id }}</p>
          <app-job-progress [jobId]="id" (statusChange)="snapshot.set($event)" />
          @if (snapshot(); as s) {
            <div class="pt-4 border-t border-line-2 text-[12px] space-y-1">
              @if (s.filename) {
                <p><span class="font-mono text-ink-3">filename:</span> {{ s.filename }}</p>
              }
              <p><span class="font-mono text-ink-3">paper_id:</span> {{ s.paper_id }}</p>
              <p><span class="font-mono text-ink-3">creado:</span> {{ s.created_at }}</p>
              <p><span class="font-mono text-ink-3">actualizado:</span> {{ s.updated_at }}</p>
            </div>
          }
          @if (paperLink(); as pid) {
            <div class="pt-4 border-t border-line-2 flex items-center gap-3">
              <a [routerLink]="['/papers', pid]" class="pill !bg-ink !text-paper !text-[11px]">Ver paper {{ pid }} →</a>
              <a routerLink="/upload" class="pill !text-[11px]">Subir otro</a>
            </div>
          }
          <a routerLink="/jobs" class="pill !text-[11px]">← Ver todos los jobs</a>
        </div>
      } @else {
        <!-- Vista de lista -->
        @if (jobs().length > 0) {
          <div class="glass rounded-3xl overflow-hidden">
            <table class="w-full text-[12px]">
              <thead class="bg-paper-2/50 font-mono text-[10px] uppercase tracking-wider text-ink-3">
                <tr>
                  <th class="text-left px-4 py-3">tipo</th>
                  <th class="text-left px-4 py-3">estado</th>
                  <th class="text-left px-4 py-3">stage</th>
                  <th class="text-left px-4 py-3">paper / target</th>
                  <th class="text-left px-4 py-3 hidden sm:table-cell">creado</th>
                  <th class="text-right px-4 py-3">job_id</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line-2">
                @for (j of jobs(); track j.job_id) {
                  <tr class="hover:bg-paper-2/40 transition-colors cursor-pointer"
                      [routerLink]="['/jobs', j.job_id]">
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2">{{ j.type || 'job' }}</td>
                    <td class="px-4 py-3">
                      <span class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider font-mono {{ statusBadge(j.status) }}">
                        <span class="w-1.5 h-1.5 rounded-full {{ statusDot(j.status) }}"
                              [class.animate-pulse]="j.status === 'running' || j.status === 'queued'"></span>
                        {{ j.status }}
                      </span>
                    </td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-2 truncate max-w-[180px]">{{ j.stage }}</td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-3">
                      @if (j.paper_id && j.paper_id !== 'ALL') {
                        <a [routerLink]="['/papers', j.paper_id]" (click)="$event.stopPropagation()" class="hover:text-jade">{{ j.paper_id }}</a>
                      } @else if (j.total) {
                        <span>{{ j.processed ?? 0 }}/{{ j.total }}</span>
                      } @else {
                        <span class="text-ink-3">—</span>
                      }
                    </td>
                    <td class="px-4 py-3 font-mono text-[11px] text-ink-3 hidden sm:table-cell">{{ formatTime(j.created_at) }}</td>
                    <td class="px-4 py-3 text-right font-mono text-[10px] text-ink-3">{{ j.job_id.slice(0, 8) }}…</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <div class="glass rounded-3xl p-6 sm:p-8 text-center space-y-3">
            <p class="text-ink-2">Todavía no hay jobs registrados.</p>
            <p class="text-[12px] text-ink-3">Sube un paper desde <a routerLink="/upload" class="underline">/upload</a> o dispara un reclassify desde <a routerLink="/reclassify" class="underline">/reclassify</a>.</p>
          </div>
        }
      }
    </section>
  `,
})
export class JobsPage implements OnInit {
  private route = inject(ActivatedRoute);
  private jobsSvc = inject(JobsService);
  activeId = signal<string | null>(null);
  snapshot = signal<JobStatus | null>(null);
  jobs = signal<JobStatus[]>([]);

  paperLink = computed<string | null>(() => {
    const s = this.snapshot();
    if (!s) return null;
    if (s.status !== 'completed') return null;
    if (!s.paper_id || s.paper_id === 'ALL') return null;
    return s.paper_id;
  });

  ngOnInit() {
    this.route.paramMap.subscribe((p) => {
      const id = p.get('id');
      this.activeId.set(id);
      if (id) {
        this.snapshot.set(null);
        this.jobsSvc.get(id).subscribe((j) => this.snapshot.set(j));
      } else {
        this.refresh();
      }
    });
  }

  refresh() {
    this.jobsSvc.list(50).subscribe((arr) => this.jobs.set(arr));
  }

  statusBadge(s: JobStatus['status']): string {
    if (s === 'completed') return 'border-jade/40 text-jade';
    if (s === 'failed') return 'border-ember/40 text-ember';
    if (s === 'running') return 'border-jade/30 text-jade';
    return 'border-line-2 text-ink-3';
  }

  statusDot(s: JobStatus['status']): string {
    if (s === 'completed') return 'bg-jade';
    if (s === 'failed') return 'bg-ember';
    if (s === 'running' || s === 'queued') return 'bg-jade';
    return 'bg-ink-3';
  }

  formatTime(iso: string): string {
    // Mostrar relativo si es muy reciente, si no la hora HH:MM.
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso.slice(11, 19);
    }
  }
}
