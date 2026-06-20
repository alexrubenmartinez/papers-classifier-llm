import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ConfigService } from '../../core/api/config.service';
import { HealthService } from '../../core/api/health.service';
import { QueryConfig, QueryConfigUpdate } from '../../core/models';
import { CostWarningComponent, formatDuration } from '../../shared/ui/cost-warning.component';

@Component({
  standalone: true,
  selector: 'app-config',
  imports: [FormsModule, CostWarningComponent],
  template: `
    <section class="space-y-6 pt-6 max-w-3xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">tema activo</p>
        <h1 class="font-display text-4xl text-ink">Configuración del scoring</h1>
        <p class="text-ink-2 mt-2 text-[14px]">Cambiar la query, los ejes, los pesos o los umbrales reordena por completo la clasificación del corpus.</p>
      </header>

      @if (isDirty()) {
        <div class="rounded-2xl border border-ember/40 bg-ember/10 px-4 py-3 flex items-center gap-3">
          <span class="w-2 h-2 rounded-full bg-ember inline-block animate-pulse"></span>
          <p class="text-[13px] text-ink">
            Hay cambios sin guardar. El ranking actual sigue reflejando la configuración previa.
          </p>
        </div>
      }

      @if (form(); as f) {
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-5">
          <div>
            <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">topic_name</label>
            <input type="text" [(ngModel)]="f.topic_name"
                   class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2.5 text-[14px]">
          </div>

          <div>
            <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">query_text · usado por SBERT y TF-IDF</label>
            <textarea [(ngModel)]="f.query_text" rows="4"
                      class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed font-mono"></textarea>
          </div>

          <div>
            <p class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">axes · keywords por eje (uno por línea)</p>
            <div class="space-y-3">
              @for (axis of axisKeys(); track axis) {
                <div>
                  <label class="block font-mono text-[11px] text-ink-2 mb-1">{{ axis }}</label>
                  <textarea [ngModel]="axisAsText(f, axis)" (ngModelChange)="updateAxisFromText(f, axis, $event)"
                            rows="2"
                            class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[12px] font-mono"></textarea>
                </div>
              }
            </div>
          </div>

          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">weight keyword</label>
              <input type="number" step="0.05" min="0" max="1" [(ngModel)]="f.weights!['keyword']"
                     class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[13px] font-mono tabular-nums">
            </div>
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">weight tfidf</label>
              <input type="number" step="0.05" min="0" max="1" [(ngModel)]="f.weights!['tfidf']"
                     class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[13px] font-mono tabular-nums">
            </div>
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">weight sbert</label>
              <input type="number" step="0.05" min="0" max="1" [(ngModel)]="f.weights!['sbert']"
                     class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[13px] font-mono tabular-nums">
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">year_range desde</label>
              <input type="number" min="1990" max="2030" [(ngModel)]="f.year_range![0]"
                     class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[13px] font-mono tabular-nums">
            </div>
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">year_range hasta</label>
              <input type="number" min="1990" max="2030" [(ngModel)]="f.year_range![1]"
                     class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-2 text-[13px] font-mono tabular-nums">
            </div>
          </div>

          <div>
            <p class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">thresholds del weighted score</p>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
              @for (key of thresholdKeys(); track key) {
                <div>
                  <label class="block font-mono text-[10px] text-ink-3 mb-1">{{ key }}</label>
                  <input type="number" step="0.05" min="0" max="1" [ngModel]="f.thresholds?.[key]"
                         (ngModelChange)="setThreshold(f, key, $event)"
                         class="w-full bg-paper-2 border border-line-2 rounded-2xl px-3 py-2 text-[12px] font-mono tabular-nums">
                </div>
              }
            </div>
          </div>

          <div class="flex flex-wrap gap-2 justify-end pt-2">
            <button (click)="save(false)" [disabled]="saving()" class="pill">Guardar (sin reclasificar)</button>
            <button (click)="askReclassify()" [disabled]="saving()" class="pill !bg-ink !text-paper">Guardar + Reclasificar</button>
          </div>
        </div>
      } @else {
        <p class="text-ink-3">Cargando config…</p>
      }

      <app-cost-warning
        [open]="askingCost()"
        title="Reclasificar 2000 papers"
        [message]="costMessage()"
        severity="info"
        [estimatedSeconds]="estimateSeconds()"
        (confirmed)="save(true); askingCost.set(false)"
        (cancelled)="askingCost.set(false)" />
    </section>
  `,
})
export class ConfigPage implements OnInit {
  private configSvc = inject(ConfigService);
  private healthSvc = inject(HealthService);
  private router = inject(Router);

  form = signal<QueryConfig | null>(null);
  /** Snapshot del config como vino del backend; sirve para detectar cambios. */
  initial = signal<string>('');
  saving = signal(false);
  askingCost = signal(false);
  papersCount = signal(0);

  isDirty = computed(() => {
    const f = this.form();
    if (!f) return false;
    return JSON.stringify(f) !== this.initial();
  });

  thresholdKeys = () => ['gold_muy', 'gold_claro', 'revisar', 'no_prioritario'];
  axisKeys = computed(() => Object.keys(this.form()?.axes || {}));

  estimateSeconds = computed(() => Math.max(2, this.papersCount() * 0.005));
  costMessage = computed(() => `Reclasifica el corpus completo con la nueva query. Solo recalcula scores (no toca embeddings).`);

  ngOnInit() {
    this.configSvc.get().subscribe((c) => {
      const loaded = { ...c, thresholds: c.thresholds ?? {} };
      this.form.set(loaded);
      this.initial.set(JSON.stringify(loaded));
    });
    this.healthSvc.health().subscribe((h) => this.papersCount.set(h.papers));
  }

  axisAsText(f: QueryConfig, axis: string): string {
    return (f.axes[axis] || []).join('\n');
  }

  updateAxisFromText(f: QueryConfig, axis: string, text: string) {
    f.axes[axis] = text.split('\n').map((s) => s.trim()).filter(Boolean);
    this.form.set({ ...f });
  }

  setThreshold(f: QueryConfig, key: string, value: number) {
    f.thresholds = { ...(f.thresholds || {}), [key]: value };
    this.form.set({ ...f });
  }

  askReclassify() {
    this.askingCost.set(true);
  }

  save(reclassify: boolean) {
    const f = this.form();
    if (!f) return;
    this.saving.set(true);
    const body: QueryConfigUpdate = {
      topic_name: f.topic_name,
      query_text: f.query_text,
      axes: f.axes,
      weights: f.weights,
      year_range: f.year_range,
      thresholds: f.thresholds || undefined,
    };
    this.configSvc.update(body, reclassify).subscribe({
      next: (updated) => {
        this.saving.set(false);
        // Reset del snapshot: ahora el form coincide con lo guardado.
        const refreshed = { ...updated, thresholds: updated.thresholds ?? {} };
        this.form.set(refreshed);
        this.initial.set(JSON.stringify(refreshed));
        if (reclassify) this.router.navigate(['/jobs']);
      },
      error: () => this.saving.set(false),
    });
  }
}
