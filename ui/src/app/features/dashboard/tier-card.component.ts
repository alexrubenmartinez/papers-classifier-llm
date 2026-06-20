import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  standalone: true,
  selector: 'app-tier-card',
  imports: [RouterLink],
  template: `
    <a [routerLink]="['/papers']" [queryParams]="queryParamsFromLink()" class="block group">
      <div class="glass rounded-3xl p-6 sm:p-8 transition-transform duration-500 ease-spring group-hover:-translate-y-1 h-full">
        <div class="flex items-baseline justify-between mb-4">
          <span class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">{{ label() }}</span>
          <span class="font-mono text-[10px] text-ink-3">{{ scoreRange() }}</span>
        </div>

        <div class="flex items-baseline gap-3">
          <span class="font-display text-6xl sm:text-7xl tabular-nums {{ color() }}">{{ count() }}</span>
          <span class="font-mono text-sm tabular-nums text-ink-2">{{ percent() }}%</span>
        </div>

        <div class="mt-5 h-1.5 rounded-full bg-paper-2 overflow-hidden">
          <div class="h-full rounded-full transition-all duration-700 ease-spring {{ barColor() }}"
               [style.width.%]="percent()"></div>
        </div>

        <p class="mt-4 text-[12px] text-ink-2 leading-relaxed">{{ description() }}</p>
      </div>
    </a>
  `,
})
export class TierCardComponent {
  label = input.required<string>();
  count = input.required<number>();
  total = input.required<number>();
  scoreRange = input.required<string>();
  description = input.required<string>();
  color = input.required<string>();
  barColor = input.required<string>();
  link = input.required<string>();

  percent = () => {
    const t = this.total();
    return t > 0 ? Math.round((this.count() / t) * 1000) / 10 : 0;
  };

  queryParamsFromLink(): Record<string, string> {
    // Extrae el query string del input `link` (ej. "/papers?tier=gold" → { tier: 'gold' })
    const url = this.link();
    const qIdx = url.indexOf('?');
    if (qIdx < 0) return {};
    const out: Record<string, string> = {};
    for (const pair of url.slice(qIdx + 1).split('&')) {
      const [k, v] = pair.split('=');
      if (k && v !== undefined) out[decodeURIComponent(k)] = decodeURIComponent(v);
    }
    return out;
  }
}
