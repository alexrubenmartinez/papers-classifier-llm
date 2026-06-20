import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { PapersService } from '../../core/api/papers.service';
import { PaperSummary, Tier, scoreToTier } from '../../core/models';
import { DecisionPillComponent } from '../../shared/ui/decision-pill.component';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';

@Component({
  standalone: true,
  selector: 'app-papers-list',
  imports: [RouterLink, FormsModule, ScoreBadgeComponent, DecisionPillComponent],
  template: `
    <section class="space-y-6 pt-6">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">papers</p>
        <h1 class="font-display text-4xl text-ink">Corpus completo</h1>
      </header>

      <!-- Filtros -->
      <div class="glass rounded-3xl p-5 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-2">
          <label class="font-mono text-[10px] uppercase tracking-wider text-ink-3">tier</label>
          <select [ngModel]="tierFilter()" (ngModelChange)="setTier($event)"
                  class="bg-paper-2 border border-line-2 rounded-full px-3 py-1.5 text-[12px] font-mono">
            <option value="all">todos</option>
            <option value="gold">Gold</option>
            <option value="silver">Silver</option>
            <option value="bronze">Bronze</option>
            <option value="out_of_range">Fuera de rango</option>
          </select>
        </div>
        <div class="flex items-center gap-2 flex-1 min-w-[200px]">
          <label class="font-mono text-[10px] uppercase tracking-wider text-ink-3">buscar</label>
          <input type="text" [ngModel]="search()" (ngModelChange)="search.set($event)" placeholder="título o paper_id…"
                 class="flex-1 bg-paper-2 border border-line-2 rounded-full px-4 py-1.5 text-[13px]">
        </div>
        <span class="font-mono text-[11px] tabular-nums text-ink-3">{{ filtered().length }} / {{ papers().length }}</span>
      </div>

      <!-- Tabla -->
      <div class="glass rounded-3xl overflow-hidden">
        <table class="w-full text-[13px]">
          <thead class="bg-paper-2/50 font-mono text-[10px] uppercase tracking-wider text-ink-3">
            <tr>
              <th class="text-left px-4 py-3">paper_id</th>
              <th class="text-left px-4 py-3">título</th>
              <th class="text-left px-4 py-3 hidden sm:table-cell">año</th>
              <th class="text-left px-4 py-3">decisión</th>
              <th class="text-right px-4 py-3">score</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line-2">
            @for (p of filtered(); track p.paper_id) {
              <tr class="hover:bg-paper-2/40 transition-colors">
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
            } @empty {
              <tr><td colspan="5" class="px-4 py-8 text-center text-ink-3 text-sm">Sin resultados.</td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
})
export class PapersListPage implements OnInit {
  private papersSvc = inject(PapersService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  papers = signal<PaperSummary[]>([]);
  tierFilter = signal<Tier | 'all'>('all');
  search = signal('');

  filtered = computed(() => {
    const q = this.search().toLowerCase().trim();
    const tf = this.tierFilter();
    return this.papers().filter((p) => {
      const tierOk = tf === 'all' || scoreToTier(p.score_final) === tf;
      const searchOk = !q || p.title.toLowerCase().includes(q) || p.paper_id.toLowerCase().includes(q);
      return tierOk && searchOk;
    });
  });

  ngOnInit() {
    // Inicializar tier desde query param ?tier=gold|silver|bronze|out_of_range
    this.route.queryParamMap.subscribe((q) => {
      const t = q.get('tier');
      if (t === 'gold' || t === 'silver' || t === 'bronze' || t === 'out_of_range' || t === 'all') {
        this.tierFilter.set(t);
      }
    });
    this.papersSvc.list(5000, 0).subscribe((p) => this.papers.set(p));
  }

  setTier(t: Tier | 'all') {
    this.tierFilter.set(t);
    // Sincronizar el query param para que el URL sea bookmarkeable.
    const queryParams = t === 'all' ? { tier: null } : { tier: t };
    this.router.navigate([], { relativeTo: this.route, queryParams, queryParamsHandling: 'merge' });
  }
}
