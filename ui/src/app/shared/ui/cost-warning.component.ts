import { Component, effect, input, output, signal } from '@angular/core';

export type CostSeverity = 'info' | 'warn' | 'danger';

const SEVERITY_STYLES: Record<CostSeverity, { ring: string; chip: string; text: string }> = {
  info:   { ring: 'border-jade/30',  chip: 'bg-jade/15 text-jade border-jade/30',   text: 'text-ink' },
  warn:   { ring: 'border-ember/40', chip: 'bg-ember/15 text-ember border-ember/40', text: 'text-ink' },
  danger: { ring: 'border-ember',    chip: 'bg-ember text-paper border-ember',       text: 'text-ember' },
};

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} seg`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} horas`;
}

@Component({
  standalone: true,
  selector: 'app-cost-warning',
  template: `
    @if (open()) {
      <div class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-paper/60 backdrop-blur-sm">
        <div class="glass rounded-3xl max-w-md w-full p-7 space-y-5 border {{ styles().ring }}">
          <div class="flex items-center gap-2">
            <span class="text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border {{ styles().chip }}">
              {{ severity() === 'danger' ? 'ATENCIÓN' : severity() === 'warn' ? 'COSTO' : 'INFO' }}
            </span>
          </div>

          <h3 class="font-display text-2xl text-ink">{{ title() }}</h3>

          <p class="text-[14px] text-ink-2 leading-relaxed">{{ message() }}</p>

          @if (estimatedSeconds() != null) {
            <div class="flex items-baseline gap-3 p-3 rounded-2xl bg-paper-2/60 border border-line-2">
              <span class="font-mono text-[10px] uppercase tracking-wider text-ink-3">tiempo estimado</span>
              <span class="font-mono text-xl font-semibold tabular-nums {{ styles().text }}">
                ~ {{ formatted() }}
              </span>
            </div>
          }

          @if (severity() === 'danger') {
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" [checked]="acknowledged()" (change)="onToggleAck($event)"
                     class="w-4 h-4 accent-ember">
              <span class="text-[12px] text-ink-2">Entiendo el costo y quiero continuar.</span>
            </label>
          }

          <div class="flex gap-2 justify-end pt-2">
            <button (click)="cancelled.emit()" class="pill">Cancelar</button>
            <button (click)="onConfirm()" [disabled]="severity() === 'danger' && !acknowledged()"
                    class="pill !bg-ink !text-paper disabled:opacity-30 disabled:cursor-not-allowed">
              Confirmar
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class CostWarningComponent {
  open = input.required<boolean>();
  title = input.required<string>();
  message = input.required<string>();
  severity = input<CostSeverity>('info');
  estimatedSeconds = input<number | null>(null);

  acknowledged = signal(false);

  confirmed = output<void>();
  cancelled = output<void>();

  constructor() {
    // Reset del checkbox cada vez que el modal se cierra.
    effect(() => {
      if (!this.open()) this.acknowledged.set(false);
    });
  }

  formatted = () => {
    const s = this.estimatedSeconds();
    return s != null ? formatDuration(s) : '';
  };

  styles = () => SEVERITY_STYLES[this.severity()];

  onToggleAck(ev: Event) {
    this.acknowledged.set((ev.target as HTMLInputElement).checked);
  }

  onConfirm() {
    if (this.severity() === 'danger' && !this.acknowledged()) return;
    this.confirmed.emit();
    this.acknowledged.set(false);
  }
}
