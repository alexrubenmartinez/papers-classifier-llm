import { Component, computed, input } from '@angular/core';
import { Tier, scoreToTier } from '../../core/models';

const TIER_CLASSES: Record<Tier, string> = {
  gold: 'bg-jade text-paper border-jade',
  silver: 'bg-ink-3/30 text-ink border-ink-3/50',
  bronze: 'bg-ember/20 text-ember border-ember/40',
  out_of_range: 'bg-paper-2 text-ink-3 border-line-2',
};

@Component({
  standalone: true,
  selector: 'app-score-badge',
  template: `
    <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-mono font-medium tabular-nums {{ tierClass() }}">
      <span class="text-[10px] uppercase tracking-wider opacity-80">score</span>
      <span class="font-semibold">{{ score() }}</span>
    </span>
  `,
})
export class ScoreBadgeComponent {
  score = input.required<number>();
  tier = computed<Tier>(() => scoreToTier(this.score()));
  tierClass = computed(() => TIER_CLASSES[this.tier()]);
}
