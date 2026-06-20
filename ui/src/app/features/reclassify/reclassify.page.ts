import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HealthService } from '../../core/api/health.service';
import { PapersService } from '../../core/api/papers.service';
import { ReclassifyJustifyMode, ReclassifyService } from '../../core/api/reclassify.service';
import { CostWarningComponent, CostSeverity } from '../../shared/ui/cost-warning.component';

@Component({
  standalone: true,
  selector: 'app-reclassify',
  imports: [FormsModule, CostWarningComponent],
  template: `
    <section class="space-y-6 pt-6 max-w-3xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">reclasificar</p>
        <h1 class="font-display text-4xl text-ink">Re-procesar el corpus</h1>
        <p class="text-ink-2 mt-2 text-[14px]">Vuelve a calcular el scoring de todos los papers contra la query activa. Opcionalmente re-extrae metadata y genera justificaciones.</p>
      </header>

      <div class="glass rounded-3xl p-6 sm:p-8 space-y-6">
        <!-- reextract -->
        <label class="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" [(ngModel)]="reextract" class="mt-1 w-4 h-4 accent-jade">
          <div>
            <p class="text-[14px] text-ink">Re-extraer metadata desde MinIO</p>
            <p class="text-[12px] text-ink-2 mt-0.5">Vuelve a leer cada PDF y re-calcula title/abstract/year/embedding.</p>
            @if (reextract()) {
              <p class="font-mono text-[11px] text-ember mt-1">+ {{ reextractFormatted() }} ({{ papers() }} papers × 0.3s)</p>
            }
          </div>
        </label>

        <!-- justify mode -->
        <div class="space-y-2">
          <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">justificación post-scoring</p>
          <div class="space-y-3">
            @for (m of modes(); track m.value) {
              <label class="flex items-start gap-3 p-4 rounded-2xl border cursor-pointer transition-colors"
                     [class.border-jade]="justify() === m.value"
                     [class.border-line-2]="justify() !== m.value">
                <input type="radio" name="just" [value]="m.value" [(ngModel)]="justifyValue"
                       (ngModelChange)="justify.set($event)" class="mt-1 accent-jade">
                <div class="flex-1">
                  <div class="flex items-baseline justify-between gap-2 flex-wrap">
                    <p class="text-[14px] text-ink">{{ m.label }}</p>
                    <span class="font-mono text-[11px] tabular-nums {{ m.severity === 'danger' ? 'text-ember' : m.severity === 'warn' ? 'text-ember' : 'text-ink-3' }}">
                      ~ {{ m.formatted }}
                    </span>
                  </div>
                  <p class="text-[12px] text-ink-2 mt-1">{{ m.desc }}</p>
                </div>
              </label>
            }
          </div>
        </div>

        <!-- Total y trigger -->
        <div class="flex items-center justify-between flex-wrap gap-3 pt-3 border-t border-line-2">
          <div>
            <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">tiempo total estimado</p>
            <p class="font-mono text-2xl tabular-nums {{ totalSeverity() === 'danger' ? 'text-ember' : 'text-ink' }}">~ {{ totalFormatted() }}</p>
          </div>
          <button (click)="trigger()" [disabled]="running()"
                  class="pill !bg-ink !text-paper disabled:opacity-30 disabled:cursor-not-allowed">
            {{ running() ? 'Disparando…' : 'Reclasificar' }}
          </button>
        </div>
      </div>

      <app-cost-warning
        [open]="askingCost()"
        [title]="warningTitle()"
        [message]="warningMessage()"
        [severity]="totalSeverity()"
        [estimatedSeconds]="totalSeconds()"
        (confirmed)="run(); askingCost.set(false)"
        (cancelled)="askingCost.set(false)" />
    </section>
  `,
})
export class ReclassifyPage implements OnInit {
  private healthSvc = inject(HealthService);
  private papersSvc = inject(PapersService);
  private reclSvc = inject(ReclassifyService);
  private router = inject(Router);

  papers = signal(0);
  goldCount = signal(0);
  reextract = signal(false);
  justify = signal<ReclassifyJustifyMode>('none');
  justifyValue: ReclassifyJustifyMode = 'none';
  running = signal(false);
  askingCost = signal(false);

  reextractSeconds = computed(() => this.papers() * 0.3);
  reextractFormatted = computed(() => this.fmt(this.reextractSeconds()));
  scoringSeconds = computed(() => Math.max(2, this.papers() * 0.01));

  justifySeconds = computed(() => {
    if (this.justify() === 'none') return 0;
    if (this.justify() === 'gold_only') return this.goldCount() * 15;
    return this.papers() * 15;
  });

  totalSeconds = computed(() =>
    this.scoringSeconds() + (this.reextract() ? this.reextractSeconds() : 0) + this.justifySeconds()
  );

  totalSeverity = computed<CostSeverity>(() => {
    const s = this.totalSeconds();
    if (s > 3600) return 'danger';
    if (s > 600) return 'warn';
    return 'info';
  });

  totalFormatted = computed(() => this.fmt(this.totalSeconds()));
  warningTitle = computed(() => this.justify() === 'all' ? 'Reclasificar con justify=all' : 'Reclasificar el corpus');
  warningMessage = computed(() => {
    const j = this.justify();
    if (j === 'all') return `Esto genera una justificación con Ollama para CADA paper del corpus (${this.papers()} papers). En CPU es muy lento.`;
    if (j === 'gold_only') return `Justifica solo los ${this.goldCount()} papers Gold (score ≥ 4) tras el reclassify.`;
    if (this.reextract()) return `Vuelve a leer ${this.papers()} PDFs desde MinIO y recalcula embeddings.`;
    return 'Recalcula scores del corpus contra la query activa. Embeddings se reusan.';
  });

  modes = computed<Array<{ value: ReclassifyJustifyMode; label: string; desc: string; formatted: string; severity: CostSeverity }>>(() => {
    return [
      { value: 'none', label: 'Sin justificar', desc: 'Solo scoring. Es lo rápido — ideal para iterar sobre el tema.', formatted: this.fmt(0), severity: 'info' },
      { value: 'gold_only', label: `Solo Gold (~${this.goldCount()} papers)`, desc: 'Justifica con Ollama solo los papers que terminaron en Gold.', formatted: this.fmt(this.goldCount() * 15), severity: this.goldCount() * 15 > 600 ? 'warn' : 'info' },
      { value: 'all', label: `Todos (${this.papers()} papers)`, desc: 'Justifica con Ollama el corpus completo. Carísimo en tiempo en CPU.', formatted: this.fmt(this.papers() * 15), severity: this.papers() * 15 > 3600 ? 'danger' : 'warn' },
    ];
  });

  ngOnInit() {
    this.healthSvc.health().subscribe((h) => this.papers.set(h.papers));
    this.papersSvc.list(2000, 4).subscribe((p) => this.goldCount.set(p.length));
  }

  trigger() {
    // Sin warning si es rapido y no es justify all.
    if (this.justify() === 'none' && !this.reextract()) {
      this.run();
      return;
    }
    this.askingCost.set(true);
  }

  run() {
    this.running.set(true);
    this.reclSvc.run({ reextract: this.reextract(), justify: this.justify() }).subscribe({
      next: (r) => {
        this.running.set(false);
        this.router.navigate(['/jobs', r.job_id]);
      },
      error: () => this.running.set(false),
    });
  }

  private fmt(s: number): string {
    if (s < 60) return `${Math.round(s)} seg`;
    if (s < 3600) return `${(s / 60).toFixed(1)} min`;
    return `${(s / 3600).toFixed(1)} horas`;
  }
}
