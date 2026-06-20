import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { RankingService } from '../../core/api/ranking.service';
import { PaperSummary } from '../../core/models';
import { DecisionPillComponent } from '../../shared/ui/decision-pill.component';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';

@Component({
  standalone: true,
  selector: 'app-ranking',
  imports: [RouterLink, FormsModule, ScoreBadgeComponent, DecisionPillComponent],
  template: `
    <section class="space-y-6 pt-6">
      <header class="flex items-baseline justify-between flex-wrap gap-4">
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">ranking</p>
          <h1 class="font-display text-4xl text-ink">Top {{ topN }}</h1>
        </div>
        <div class="flex items-center gap-2">
          <label class="font-mono text-[10px] uppercase tracking-wider text-ink-3">top</label>
          <select [(ngModel)]="topN" (ngModelChange)="reload()"
                  class="bg-paper-2 border border-line-2 rounded-full px-3 py-1.5 text-[12px] font-mono">
            <option [ngValue]="5">5</option>
            <option [ngValue]="10">10</option>
            <option [ngValue]="25">25</option>
            <option [ngValue]="50">50</option>
          </select>
        </div>
      </header>

      <div class="glass rounded-3xl overflow-hidden">
        <table class="w-full text-[13px]">
          <thead class="bg-paper-2/50 font-mono text-[10px] uppercase tracking-wider text-ink-3">
            <tr>
              <th class="text-left px-4 py-3 w-12">#</th>
              <th class="text-left px-4 py-3">paper_id</th>
              <th class="text-left px-4 py-3">título</th>
              <th class="text-left px-4 py-3 hidden sm:table-cell">año</th>
              <th class="text-left px-4 py-3">decisión</th>
              <th class="text-right px-4 py-3">score</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line-2">
            @for (p of papers(); track p.paper_id; let i = $index) {
              <tr class="hover:bg-paper-2/40 transition-colors">
                <td class="px-4 py-3 font-mono text-ink-3 tabular-nums">{{ i + 1 }}</td>
                <td class="px-4 py-3 font-mono text-[11px] text-ink-3">
                  <a [routerLink]="['/papers', p.paper_id]" class="hover:text-jade">{{ p.paper_id }}</a>
                </td>
                <td class="px-4 py-3 max-w-[400px]">
                  <a [routerLink]="['/papers', p.paper_id]" class="text-ink hover:text-jade truncate block">{{ p.title }}</a>
                </td>
                <td class="px-4 py-3 font-mono tabular-nums text-ink-2 hidden sm:table-cell">{{ p.year }}</td>
                <td class="px-4 py-3"><app-decision-pill [decision]="p.decision" /></td>
                <td class="px-4 py-3 text-right"><app-score-badge [score]="p.score_final" /></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
})
export class RankingPage implements OnInit {
  private rankingSvc = inject(RankingService);
  papers = signal<PaperSummary[]>([]);
  topN = 10;

  ngOnInit() { this.reload(); }

  reload() {
    this.rankingSvc.top(this.topN).subscribe((p) => this.papers.set(p));
  }
}
