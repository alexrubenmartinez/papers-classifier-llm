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
    <section class="space-y-6 pt-6 max-w-3xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">jobs</p>
        <h1 class="font-display text-4xl text-ink">{{ activeId() ? 'Job activo' : 'Jobs' }}</h1>
      </header>

      @if (activeId(); as id) {
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

          <!-- CTA al paper resultante (solo para jobs tipo ingest) -->
          @if (paperLink(); as pid) {
            <div class="pt-4 border-t border-line-2 flex items-center gap-3">
              <a [routerLink]="['/papers', pid]" class="pill !bg-ink !text-paper !text-[11px]">Ver paper {{ pid }} →</a>
              <a routerLink="/upload" class="pill !text-[11px]">Subir otro</a>
            </div>
          }

          <a routerLink="/jobs" class="pill !text-[11px]">Ver todos →</a>
        </div>
      } @else {
        <div class="glass rounded-3xl p-6 sm:p-8">
          <p class="text-ink-2">
            Para ver el progreso de un job, accedé a su URL directa (las páginas de upload y reclassify te redirigen automáticamente).
            <br><br>
            <span class="font-mono text-[11px] text-ink-3">Ejemplo: /jobs/&lt;job_id&gt;</span>
          </p>
        </div>
      }
    </section>
  `,
})
export class JobsPage implements OnInit {
  private route = inject(ActivatedRoute);
  private jobsSvc = inject(JobsService);
  activeId = signal<string | null>(null);
  snapshot = signal<JobStatus | null>(null);

  /**
   * Devuelve el paper_id si el job es tipo ingest, ya termino, y apunta a un paper concreto
   * (no "ALL"). Los jobs reclassify/justify/import no tienen un paper unico al que apuntar.
   */
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
      if (id) this.jobsSvc.get(id).subscribe((j) => this.snapshot.set(j));
    });
  }
}
