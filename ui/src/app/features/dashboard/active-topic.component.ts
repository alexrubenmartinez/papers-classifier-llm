import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { QueryConfig } from '../../core/models';

@Component({
  standalone: true,
  selector: 'app-active-topic',
  imports: [RouterLink],
  template: `
    @if (config(); as cfg) {
      <div class="space-y-4">
        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-1">tema activo</p>
          <h3 class="font-display text-2xl text-ink">{{ cfg.topic_name }}</h3>
        </div>

        <p class="text-[13px] text-ink-2 leading-relaxed line-clamp-3">{{ cfg.query_text }}</p>

        <div>
          <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-2">ejes</p>
          <div class="flex flex-wrap gap-1.5">
            @for (axis of axes(); track axis) {
              <span class="pill !text-[10px] !py-0.5 !px-2">{{ axis }}</span>
            }
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 pt-2">
          <a routerLink="/config" class="pill !text-[11px]">Editar tema</a>
          <a routerLink="/reclassify" class="pill pill-mono !text-[11px]">Reclasificar</a>
        </div>
      </div>
    } @else {
      <p class="font-mono text-[11px] text-ink-3">Cargando tema…</p>
    }
  `,
})
export class ActiveTopicComponent {
  config = input.required<QueryConfig | null>();

  axes = () => Object.keys(this.config()?.axes || {});
}
