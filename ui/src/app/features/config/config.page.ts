import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ConfigService } from '../../core/api/config.service';
import { HealthService } from '../../core/api/health.service';
import { QueryConfig, QueryConfigUpdate } from '../../core/models';
import { CostWarningComponent } from '../../shared/ui/cost-warning.component';
import { KeywordChipsComponent } from '../../shared/ui/keyword-chips.component';

/**
 * Presets para empezar rapido. Si el examinador no sabe que poner, click.
 */
const PRESETS: Record<string, Partial<QueryConfig>> = {
  zero_trust: {
    topic_name: 'Zero Trust + IA en Ciberseguridad',
    query_text:
      'Zero trust architecture for cybersecurity threat detection using artificial intelligence machine learning in cloud and hybrid environments. Includes NIST 800-207, ZTNA, microsegmentation, intrusion detection, anomaly detection, and AI-powered security.',
    axes: {
      keywords: [
        'zero trust', 'zero-trust', 'ztna', 'beyondcorp', 'nist 800-207', 'microsegmentation',
        'cybersecurity', 'cyber security', 'cloud security',
        'threat detection', 'intrusion detection', 'anomaly detection',
        'artificial intelligence', 'machine learning', 'deep learning', 'ai-powered',
      ],
    },
  },
  blockchain: {
    topic_name: 'Blockchain + DLT financiero',
    query_text:
      'Blockchain distributed ledger technology smart contracts cryptocurrency DeFi for secure financial systems and transaction verification.',
    axes: {
      keywords: [
        'blockchain', 'distributed ledger', 'dlt', 'smart contract', 'ethereum', 'bitcoin',
        'cryptocurrency', 'defi', 'fintech',
        'consensus', 'proof of stake', 'proof of work',
        'cryptography', 'zero knowledge', 'merkle',
      ],
    },
  },
  vacio: {
    topic_name: 'Tema personalizado',
    query_text: '',
    axes: { keywords: [] },
  },
};

@Component({
  standalone: true,
  selector: 'app-config',
  imports: [FormsModule, CostWarningComponent, KeywordChipsComponent],
  template: `
    <section class="space-y-6 pt-6 max-w-4xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">tema activo</p>
        <h1 class="font-display text-4xl text-ink">Configuración del scoring</h1>
        <p class="text-ink-2 mt-2 text-[14px]">
          Cambiá la query, las keywords, los pesos o los umbrales y el corpus se reordena.
          Empezá con un preset o desde cero.
        </p>
      </header>

      @if (isDirty()) {
        <div class="rounded-2xl border border-ember/40 bg-ember/10 px-4 py-3 flex items-center gap-3">
          <span class="w-2 h-2 rounded-full bg-ember inline-block animate-pulse"></span>
          <p class="text-[13px] text-ink">
            Cambios sin guardar — el ranking actual todavía refleja la configuración previa.
          </p>
        </div>
      }

      <!-- Presets -->
      <div class="glass rounded-3xl p-5 flex flex-wrap items-center gap-3">
        <span class="font-mono text-[10px] uppercase tracking-wider text-ink-3 mr-1">presets</span>
        <button (click)="applyPreset('zero_trust')" class="pill !text-[11px]">Zero Trust + IA</button>
        <button (click)="applyPreset('blockchain')" class="pill !text-[11px]">Blockchain + DLT</button>
        <button (click)="applyPreset('vacio')" class="pill !text-[11px]">Empezar de cero</button>
      </div>

      @if (form(); as f) {
        <!-- Identidad del tema -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-5">
          <div>
            <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">nombre del tema</label>
            <input type="text" [(ngModel)]="f.topic_name"
                   (ngModelChange)="touch(f)"
                   placeholder="ej. Zero Trust + IA en Ciberseguridad"
                   class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-3 text-[16px] font-display">
          </div>

          <div>
            <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-2">
              query natural — guía al SBERT y al TF-IDF
            </label>
            <textarea [(ngModel)]="f.query_text"
                      (ngModelChange)="touch(f)"
                      rows="3"
                      placeholder="Describe el tema en una oración natural en inglés (es el lenguaje del modelo SBERT)."
                      class="w-full bg-paper-2 border border-line-2 rounded-2xl px-4 py-3 text-[13px] leading-relaxed"></textarea>
            <p class="font-mono text-[10px] text-ink-3 mt-1">{{ f.query_text.length }} caracteres</p>
          </div>
        </div>

        <!-- Keywords -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-4">
          <div class="flex items-baseline justify-between gap-3">
            <div>
              <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3">palabras clave</label>
              <p class="text-[12px] text-ink-2 mt-1">Una sola caja. Tipea + enter (o pegá con comas).</p>
            </div>
            <button (click)="toggleAdvanced()" class="pill !text-[10px]">
              {{ advanced() ? 'Vista simple' : 'Vista avanzada (ejes)' }}
            </button>
          </div>

          @if (!advanced()) {
            <app-keyword-chips
              [keywords]="primaryKeywords(f)"
              placeholder="ej. zero trust, ai-powered, threat detection…"
              (changed)="setPrimaryKeywords(f, $event)" />
          } @else {
            <p class="text-[12px] text-ink-3">
              Modo avanzado: las keywords se agrupan en <span class="font-mono">ejes temáticos</span>.
              El scoring usa cobertura — un paper debe matchear al menos 1 keyword de cada eje para
              tener keyword_score=1.0.
            </p>
            @for (axis of axisKeys(f); track axis) {
              <div class="space-y-2 pt-3 border-t border-line-2">
                <div class="flex items-center justify-between gap-2">
                  <input type="text" [value]="axis" (change)="renameAxis(f, axis, $any($event.target).value)"
                         class="font-mono text-[12px] uppercase tracking-wider bg-transparent border-b border-line-2 px-1 py-0.5 text-ink-2 focus:border-jade outline-none">
                  <button (click)="removeAxis(f, axis)" class="pill !text-[10px]">Borrar eje</button>
                </div>
                <app-keyword-chips
                  [keywords]="f.axes[axis] || []"
                  (changed)="setAxis(f, axis, $event)" />
              </div>
            }
            <button (click)="addAxis(f)" class="pill !text-[11px]">+ Agregar eje</button>
          }
        </div>

        <!-- Pesos del score híbrido -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-5">
          <div class="flex items-baseline justify-between">
            <div>
              <h3 class="font-display text-xl text-ink">Pesos del score híbrido</h3>
              <p class="text-[12px] text-ink-2 mt-1">El weighted se compone de tres señales. Pueden no sumar 1 — se interpreta como mix.</p>
            </div>
            <span class="font-mono text-[11px] tabular-nums text-ink-3">
              suma {{ weightsSum(f).toFixed(2) }}
            </span>
          </div>

          @for (key of weightKeys; track key) {
            <div class="space-y-2">
              <div class="flex items-baseline justify-between">
                <label class="font-mono text-[11px] uppercase tracking-wider text-ink-2">{{ key }}</label>
                <span class="font-mono text-[13px] tabular-nums text-ink">{{ (f.weights?.[key] ?? 0).toFixed(2) }}</span>
              </div>
              <input type="range" min="0" max="1" step="0.05"
                     [ngModel]="f.weights?.[key] ?? 0"
                     (ngModelChange)="setWeight(f, key, $event)"
                     class="w-full accent-jade">
              <p class="font-mono text-[10px] text-ink-3">{{ weightHints[key] }}</p>
            </div>
          }
        </div>

        <!-- Año -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-4">
          <h3 class="font-display text-xl text-ink">Ventana temporal</h3>
          <p class="text-[12px] text-ink-2">Papers fuera del rango quedan con score 0 (fuera de rango).</p>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="flex items-baseline justify-between mb-1">
                <label class="font-mono text-[10px] uppercase tracking-wider text-ink-3">desde</label>
                <span class="font-mono text-[14px] tabular-nums text-ink">{{ f.year_range?.[0] }}</span>
              </div>
              <input type="range" min="1990" max="2030" step="1"
                     [ngModel]="f.year_range?.[0] ?? 2016"
                     (ngModelChange)="setYearFrom(f, $event)"
                     class="w-full accent-jade">
            </div>
            <div>
              <div class="flex items-baseline justify-between mb-1">
                <label class="font-mono text-[10px] uppercase tracking-wider text-ink-3">hasta</label>
                <span class="font-mono text-[14px] tabular-nums text-ink">{{ f.year_range?.[1] }}</span>
              </div>
              <input type="range" min="1990" max="2030" step="1"
                     [ngModel]="f.year_range?.[1] ?? 2026"
                     (ngModelChange)="setYearTo(f, $event)"
                     class="w-full accent-jade">
            </div>
          </div>
        </div>

        <!-- Umbrales -->
        <div class="glass rounded-3xl p-6 sm:p-8 space-y-5">
          <div>
            <h3 class="font-display text-xl text-ink">Umbrales de decisión</h3>
            <p class="text-[12px] text-ink-2 mt-1">
              Dónde cortan los tiers sobre el weighted score (0–1).
            </p>
          </div>

          <!-- Barra visual de tiers -->
          <div class="relative h-7 rounded-full overflow-hidden border border-line-2 bg-paper-2">
            <div class="absolute inset-y-0 left-0 bg-ember/30" [style.width.%]="thresholdPct(f, 'no_prioritario') * 100"></div>
            <div class="absolute inset-y-0 bg-ember/50"
                 [style.left.%]="thresholdPct(f, 'no_prioritario') * 100"
                 [style.width.%]="(thresholdPct(f, 'revisar') - thresholdPct(f, 'no_prioritario')) * 100"></div>
            <div class="absolute inset-y-0 bg-ink-3/40"
                 [style.left.%]="thresholdPct(f, 'revisar') * 100"
                 [style.width.%]="(thresholdPct(f, 'gold_claro') - thresholdPct(f, 'revisar')) * 100"></div>
            <div class="absolute inset-y-0 bg-jade/40"
                 [style.left.%]="thresholdPct(f, 'gold_claro') * 100"
                 [style.width.%]="(thresholdPct(f, 'gold_muy') - thresholdPct(f, 'gold_claro')) * 100"></div>
            <div class="absolute inset-y-0 bg-jade"
                 [style.left.%]="thresholdPct(f, 'gold_muy') * 100"
                 [style.right]="0"></div>
            <div class="absolute inset-0 flex items-center justify-between px-3 text-[10px] font-mono uppercase tracking-wider">
              <span class="text-ember">Excluido · No prio</span>
              <span class="text-ink">Revisar</span>
              <span class="text-jade">Gold</span>
            </div>
          </div>

          @for (key of thresholdKeys; track key) {
            <div class="space-y-2">
              <div class="flex items-baseline justify-between">
                <label class="font-mono text-[11px] uppercase tracking-wider text-ink-2">{{ thresholdLabel[key] }}</label>
                <span class="font-mono text-[13px] tabular-nums text-ink">{{ (f.thresholds?.[key] ?? 0).toFixed(2) }}</span>
              </div>
              <input type="range" min="0" max="1" step="0.01"
                     [ngModel]="f.thresholds?.[key] ?? 0"
                     (ngModelChange)="setThreshold(f, key, $event)"
                     class="w-full accent-jade">
            </div>
          }
        </div>

        <!-- Acciones -->
        <div class="glass rounded-3xl p-6 flex flex-wrap items-center justify-end gap-2">
          <button (click)="save(false)" [disabled]="saving()" class="pill">Guardar (sin reclasificar)</button>
          <button (click)="askReclassify()" [disabled]="saving()" class="pill !bg-ink !text-paper">
            Guardar + Reclasificar
          </button>
        </div>
      } @else {
        <p class="text-ink-3">Cargando config…</p>
      }

      <app-cost-warning
        [open]="askingCost()"
        title="Reclasificar todo el corpus"
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
  initial = signal<string>('');
  saving = signal(false);
  askingCost = signal(false);
  papersCount = signal(0);
  advanced = signal(false);

  readonly weightKeys = ['keyword', 'tfidf', 'sbert'] as const;
  readonly weightHints: Record<string, string> = {
    keyword: 'Cobertura de las palabras clave en title + abstract.',
    tfidf: 'Similitud léxica con la query (más sensible al vocabulario exacto).',
    sbert: 'Similitud semántica con la query (entiende sinónimos y contexto).',
  };
  readonly thresholdKeys = ['gold_muy', 'gold_claro', 'revisar', 'no_prioritario'] as const;
  readonly thresholdLabel: Record<string, string> = {
    gold_muy: 'Score 5 · Gold muy relacionado ≥',
    gold_claro: 'Score 4 · Gold claramente relacionado ≥',
    revisar: 'Score 3 · Revisar parcial ≥',
    no_prioritario: 'Score 2 · No prioritario ≥',
  };

  isDirty = computed(() => {
    const f = this.form();
    if (!f) return false;
    return JSON.stringify(f) !== this.initial();
  });

  estimateSeconds = computed(() => Math.max(2, this.papersCount() * 0.01));
  costMessage = computed(
    () => `Recalcula scores del corpus contra la nueva query. Embeddings se reusan.`,
  );

  ngOnInit() {
    this.configSvc.get().subscribe((c) => {
      const loaded = { ...c, thresholds: c.thresholds ?? {} };
      this.form.set(loaded);
      this.initial.set(JSON.stringify(loaded));
      // Si vienen >1 ejes del backend, mostrar modo avanzado por defecto.
      if (Object.keys(loaded.axes).length > 1) this.advanced.set(true);
    });
    this.healthSvc.health().subscribe((h) => this.papersCount.set(h.papers));
  }

  touch(f: QueryConfig) {
    this.form.set({ ...f });
  }

  toggleAdvanced() {
    const f = this.form();
    if (!f) return;
    if (!this.advanced()) {
      // Pasando a avanzado: si solo hay 1 eje, dejar tal cual.
      this.advanced.set(true);
    } else {
      // Pasando a simple: combinar todas las keywords en un solo eje.
      const all = Object.values(f.axes).flat();
      f.axes = { keywords: Array.from(new Set(all)) };
      this.advanced.set(false);
      this.form.set({ ...f });
    }
  }

  primaryKeywords(f: QueryConfig): string[] {
    // En modo simple, lo de cualquiera de los ejes; si hay varios, los unimos.
    if (this.advanced()) return [];
    const keys = Object.keys(f.axes);
    if (keys.length === 0) return [];
    if (keys.length === 1) return f.axes[keys[0]];
    return Array.from(new Set(Object.values(f.axes).flat()));
  }

  setPrimaryKeywords(f: QueryConfig, kws: string[]) {
    f.axes = { keywords: kws };
    this.form.set({ ...f });
  }

  axisKeys(f: QueryConfig): string[] {
    return Object.keys(f.axes);
  }

  setAxis(f: QueryConfig, name: string, kws: string[]) {
    f.axes = { ...f.axes, [name]: kws };
    this.form.set({ ...f });
  }

  renameAxis(f: QueryConfig, oldName: string, newName: string) {
    const trimmed = newName.trim().toLowerCase().replace(/\s+/g, '_');
    if (!trimmed || trimmed === oldName) return;
    const next: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(f.axes)) {
      next[k === oldName ? trimmed : k] = v;
    }
    f.axes = next;
    this.form.set({ ...f });
  }

  addAxis(f: QueryConfig) {
    let n = 1;
    while (f.axes[`eje_${n}`]) n++;
    f.axes = { ...f.axes, [`eje_${n}`]: [] };
    this.form.set({ ...f });
  }

  removeAxis(f: QueryConfig, name: string) {
    const next = { ...f.axes };
    delete next[name];
    if (Object.keys(next).length === 0) next['keywords'] = [];
    f.axes = next;
    this.form.set({ ...f });
  }

  weightsSum(f: QueryConfig): number {
    const w = f.weights || {};
    return (w['keyword'] ?? 0) + (w['tfidf'] ?? 0) + (w['sbert'] ?? 0);
  }

  setWeight(f: QueryConfig, key: string, v: number) {
    f.weights = { ...(f.weights || {}), [key]: v };
    this.form.set({ ...f });
  }

  setYearFrom(f: QueryConfig, v: number) {
    const range = f.year_range || [2016, 2026];
    f.year_range = [v, Math.max(v, range[1])];
    this.form.set({ ...f });
  }

  setYearTo(f: QueryConfig, v: number) {
    const range = f.year_range || [2016, 2026];
    f.year_range = [Math.min(range[0], v), v];
    this.form.set({ ...f });
  }

  setThreshold(f: QueryConfig, key: string, v: number) {
    f.thresholds = { ...(f.thresholds || {}), [key]: v };
    this.form.set({ ...f });
  }

  thresholdPct(f: QueryConfig, key: string): number {
    return Math.max(0, Math.min(1, f.thresholds?.[key] ?? 0));
  }

  applyPreset(name: keyof typeof PRESETS) {
    const f = this.form();
    if (!f) return;
    const preset = PRESETS[name];
    const updated: QueryConfig = {
      ...f,
      topic_name: preset.topic_name ?? f.topic_name,
      query_text: preset.query_text ?? f.query_text,
      axes: preset.axes ?? f.axes,
    };
    this.form.set(updated);
    // Aplicar preset implica modo simple (1 eje "keywords").
    this.advanced.set(false);
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
        const refreshed = { ...updated, thresholds: updated.thresholds ?? {} };
        this.form.set(refreshed);
        this.initial.set(JSON.stringify(refreshed));
        if (reclassify) this.router.navigate(['/jobs']);
      },
      error: () => this.saving.set(false),
    });
  }
}
