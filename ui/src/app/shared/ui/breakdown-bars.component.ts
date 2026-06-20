import { Component, input } from '@angular/core';
import { ScoreBreakdown } from '../../core/models';

interface Row {
  label: string;
  hint: string;
  value: number;
  color: string;
  emphasis?: boolean;
}

@Component({
  standalone: true,
  selector: 'app-breakdown-bars',
  template: `
    <div class="space-y-3">
      @for (row of rows(); track row.label) {
        <div>
          <div class="flex items-baseline justify-between text-[12px] mb-1">
            <div class="flex items-baseline gap-2">
              <span class="font-mono uppercase tracking-wider text-[10px] text-ink-3">{{ row.label }}</span>
              <span class="text-ink-3 text-[11px]">· {{ row.hint }}</span>
            </div>
            <span class="font-mono tabular-nums {{ row.emphasis ? 'text-ink font-semibold' : 'text-ink-2' }}">{{ (row.value * 100).toFixed(1) }}%</span>
          </div>
          <div class="h-2 rounded-full bg-paper-2 overflow-hidden">
            <div class="h-full rounded-full transition-all duration-700 ease-spring"
                 [style.width.%]="row.value * 100"
                 [class]="row.color"></div>
          </div>
        </div>
      }
    </div>
  `,
})
export class BreakdownBarsComponent {
  breakdown = input.required<ScoreBreakdown>();

  rows = (): Row[] => {
    const b = this.breakdown();
    return [
      { label: 'keyword', hint: '4 ejes temáticos', value: b.keyword, color: 'bg-ember/60' },
      { label: 'tfidf', hint: 'similitud léxica', value: b.tfidf, color: 'bg-ink-3' },
      { label: 'sbert', hint: 'similitud semántica', value: b.sbert, color: 'bg-jade/60' },
      { label: 'weighted', hint: 'score final ponderado', value: b.weighted, color: 'bg-jade', emphasis: true },
    ];
  };
}
