import { Component, computed, input } from '@angular/core';
import { Tier } from '../../core/models';

function decisionToTier(decision: string): Tier {
  const d = decision.toLowerCase();
  if (d.startsWith('gold')) return 'gold';
  if (d.includes('revisar')) return 'silver';
  if (d.includes('fuera')) return 'out_of_range';
  return 'bronze';
}

const TIER_STYLES: Record<Tier, { bg: string; dot: string }> = {
  gold:         { bg: 'border-jade/40 text-jade',         dot: 'bg-jade' },
  silver:       { bg: 'border-ink-3/50 text-ink-2',       dot: 'bg-ink-3' },
  bronze:       { bg: 'border-ember/40 text-ember',       dot: 'bg-ember' },
  out_of_range: { bg: 'border-line-2 text-ink-3',         dot: 'bg-ink-3/50' },
};

@Component({
  standalone: true,
  selector: 'app-decision-pill',
  template: `
    <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] uppercase tracking-wider font-mono whitespace-nowrap {{ styles().bg }}">
      <span class="w-1.5 h-1.5 rounded-full inline-block {{ styles().dot }}"></span>
      <span>{{ decision() }}</span>
    </span>
  `,
})
export class DecisionPillComponent {
  decision = input.required<string>();
  styles = computed(() => TIER_STYLES[decisionToTier(this.decision())]);
}
