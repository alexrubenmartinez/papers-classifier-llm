import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ConfigService } from '../../core/api/config.service';
import { HealthService } from '../../core/api/health.service';
import { PapersService } from '../../core/api/papers.service';
import { RankingService } from '../../core/api/ranking.service';
import { HealthStatus, PaperSummary, QueryConfig } from '../../core/models';
import { DecisionPillComponent } from '../../shared/ui/decision-pill.component';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';
import { ActiveTopicComponent } from './active-topic.component';
import { DonutChartComponent } from './donut-chart.component';
import { TierCardComponent } from './tier-card.component';

@Component({
  standalone: true,
  selector: 'app-dashboard',
  imports: [
    RouterLink,
    TierCardComponent,
    DonutChartComponent,
    ActiveTopicComponent,
    ScoreBadgeComponent,
    DecisionPillComponent,
  ],
  template: `
    <section class="space-y-8">
      <!-- Hero -->
      <header class="space-y-2 pt-6">
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">dashboard</p>
        <h1 class="font-display text-4xl sm:text-5xl text-ink">
          Estado del corpus.
        </h1>
        <p class="text-ink-2 max-w-2xl">
          {{ health()?.papers ?? '—' }} papers procesados.
          Pipeline en {{ health()?.tfidf_fitted ? 'estado normal' : 'iniciando' }}.
        </p>
      </header>

      <!-- 3 tarjetas Bronze/Silver/Gold -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <app-tier-card
          label="Gold"
          [count]="counts().gold"
          [total]="totalScored()"
          scoreRange="score 4–5"
          description="Papers fuertemente alineados al tema activo. Recomendados para revisión profunda."
          color="text-jade"
          barColor="bg-jade"
          link="/papers?tier=gold"
        />
        <app-tier-card
          label="Silver"
          [count]="counts().silver"
          [total]="totalScored()"
          scoreRange="score 3"
          description="Match parcial. Requieren lectura humana para decidir si entran al corpus final."
          color="text-ink"
          barColor="bg-ink-3"
          link="/papers?tier=silver"
        />
        <app-tier-card
          label="Bronze"
          [count]="counts().bronze"
          [total]="totalScored()"
          scoreRange="score 1–2"
          description="Match débil o nulo. Descartables salvo cambio de tema."
          color="text-ember"
          barColor="bg-ember"
          link="/papers?tier=bronze"
        />
      </div>

      <!-- Donut + tema activo -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="glass rounded-3xl p-6 sm:p-8">
          <div class="flex items-baseline justify-between mb-4">
            <h2 class="font-display text-2xl text-ink">Distribución</h2>
            <span class="font-mono text-[10px] uppercase tracking-wider text-ink-3">por score 0–5</span>
          </div>
          @if (papers().length > 0) {
            <app-donut-chart [papers]="papers()" />
          } @else {
            <p class="text-ink-3 text-sm">Sin datos.</p>
          }
        </div>

        <div class="glass rounded-3xl p-6 sm:p-8">
          <app-active-topic [config]="config()" />
        </div>
      </div>

      <!-- Top-5 ranking -->
      <div class="glass rounded-3xl p-6 sm:p-8">
        <div class="flex items-baseline justify-between mb-5">
          <h2 class="font-display text-2xl text-ink">Top 5 del ranking</h2>
          <a routerLink="/ranking" class="pill !text-[11px]">Ver completo →</a>
        </div>

        @if (top5().length > 0) {
          <ul class="divide-y divide-line-2">
            @for (p of top5(); track p.paper_id) {
              <li class="py-3 flex items-center gap-4">
                <a [routerLink]="['/papers', p.paper_id]" class="flex-1 min-w-0 hover:text-jade transition-colors">
                  <p class="font-mono text-[10px] text-ink-3">{{ p.paper_id }} · {{ p.year }}</p>
                  <p class="text-[14px] text-ink truncate">{{ p.title }}</p>
                </a>
                <app-decision-pill [decision]="p.decision" />
                <app-score-badge [score]="p.score_final" />
              </li>
            }
          </ul>
        } @else {
          <p class="text-ink-3 text-sm">Sin papers todavía. Sube uno desde <a routerLink="/upload" class="underline">/upload</a>.</p>
        }
      </div>

      <!-- Estado del API -->
      <div class="glass rounded-3xl p-6 sm:p-8">
        <h2 class="font-display text-2xl text-ink mb-4">Estado del API</h2>
        @if (health(); as h) {
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-[13px]">
            <div>
              <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">papers</p>
              <p class="font-mono text-2xl tabular-nums text-ink">{{ h.papers }}</p>
            </div>
            <div>
              <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">jobs activos</p>
              <p class="font-mono text-2xl tabular-nums {{ h.jobs_in_flight > 0 ? 'text-jade' : 'text-ink' }}">{{ h.jobs_in_flight }}</p>
            </div>
            <div>
              <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">SBERT</p>
              <p class="font-mono text-[13px] {{ h.sbert_loaded ? 'text-jade' : 'text-ember' }}">{{ h.sbert_loaded ? 'cargado' : 'no listo' }}</p>
            </div>
            <div>
              <p class="font-mono text-[10px] uppercase tracking-wider text-ink-3">TF-IDF</p>
              <p class="font-mono text-[13px] {{ h.tfidf_fitted ? 'text-jade' : 'text-ember' }}">{{ h.tfidf_fitted ? 'fitted' : 'no fitted' }}</p>
            </div>
          </div>
        }
      </div>
    </section>
  `,
})
export class DashboardPage implements OnInit {
  private healthSvc = inject(HealthService);
  private papersSvc = inject(PapersService);
  private rankingSvc = inject(RankingService);
  private configSvc = inject(ConfigService);

  health = signal<HealthStatus | null>(null);
  papers = signal<PaperSummary[]>([]);
  top5 = signal<PaperSummary[]>([]);
  config = signal<QueryConfig | null>(null);

  counts = computed(() => {
    const buckets = { gold: 0, silver: 0, bronze: 0, out: 0 };
    for (const p of this.papers()) {
      if (p.score_final === 0) buckets.out++;
      else if (p.score_final >= 4) buckets.gold++;
      else if (p.score_final === 3) buckets.silver++;
      else buckets.bronze++;
    }
    return buckets;
  });

  totalScored = computed(() => {
    const c = this.counts();
    return c.gold + c.silver + c.bronze + c.out;
  });

  ngOnInit() {
    this.healthSvc.health().subscribe((h) => this.health.set(h));
    this.papersSvc.list(2000, 0).subscribe((p) => this.papers.set(p));
    this.rankingSvc.top(5).subscribe((r) => this.top5.set(r));
    this.configSvc.get().subscribe((c) => this.config.set(c));
  }
}
