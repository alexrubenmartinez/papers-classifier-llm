import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { JustifyService } from '../../core/api/justify.service';
import { PapersService } from '../../core/api/papers.service';
import { Paper } from '../../core/models';
import { BreakdownBarsComponent } from '../../shared/ui/breakdown-bars.component';
import { DecisionPillComponent } from '../../shared/ui/decision-pill.component';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';

@Component({
  standalone: true,
  selector: 'app-paper-detail',
  imports: [RouterLink, ScoreBadgeComponent, DecisionPillComponent, BreakdownBarsComponent],
  template: `
    <section class="space-y-6 pt-6 max-w-3xl">
      <a routerLink="/papers" class="pill !text-[11px]">← Volver a papers</a>

      @if (paper(); as p) {
        <header class="space-y-3">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-mono text-[11px] text-ink-3">{{ p.paper_id }} · {{ p.year }}</span>
            <app-decision-pill [decision]="p.decision" />
            <app-score-badge [score]="p.score_final" />
          </div>
          <h1 class="font-display text-3xl sm:text-4xl text-ink">{{ p.title }}</h1>
        </header>

        @if (p.abstract) {
          <div class="glass rounded-3xl p-6 sm:p-8">
            <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-3">abstract</p>
            <p class="text-[14px] text-ink-2 leading-relaxed">{{ p.abstract }}</p>
          </div>
        }

        <div class="glass rounded-3xl p-6 sm:p-8">
          <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-4">breakdown del score</p>
          <app-breakdown-bars [breakdown]="p.score_breakdown" />
        </div>

        <div class="glass rounded-3xl p-6 sm:p-8 space-y-4">
          <div class="flex items-baseline justify-between gap-3 flex-wrap">
            <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">justificación con Ollama</p>
            <button (click)="generate()" [disabled]="justifying()"
                    class="pill !text-[11px]" title="~15s con qwen2.5:1.5b en CPU">
              {{ justifying() ? 'Generando…' : (p.justification ? 'Regenerar' : 'Generar') }}
            </button>
          </div>
          @if (p.justification) {
            <p class="text-[14px] text-ink-2 leading-relaxed">{{ p.justification }}</p>
          } @else {
            <p class="text-[13px] text-ink-3">
              Sin justificación generada. El botón llama al LLM y guarda la respuesta para futuras visitas. <br>
              <span class="font-mono text-[11px]">≈ 15s por paper (qwen2.5:1.5b CPU).</span>
            </p>
          }
        </div>
      } @else {
        <p class="text-ink-3">Cargando…</p>
      }
    </section>
  `,
})
export class PaperDetailPage implements OnInit {
  private route = inject(ActivatedRoute);
  private papersSvc = inject(PapersService);
  private justifySvc = inject(JustifyService);

  paper = signal<Paper | null>(null);
  justifying = signal(false);

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.papersSvc.get(id).subscribe((p) => this.paper.set(p));
  }

  generate() {
    const p = this.paper();
    if (!p) return;
    this.justifying.set(true);
    this.justifySvc.one(p.paper_id).subscribe({
      next: (r) => {
        this.paper.update((cur) => cur ? { ...cur, justification: r.justification } : cur);
        this.justifying.set(false);
      },
      error: () => this.justifying.set(false),
    });
  }
}
