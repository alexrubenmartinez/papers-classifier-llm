import { Component, computed, input } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { EChartsCoreOption } from 'echarts/core';
import { PaperSummary } from '../../core/models';

const SCORE_META: Record<number, { label: string; color: string }> = {
  5: { label: '5 · Gold muy',         color: '#1F4438' },
  4: { label: '4 · Gold claramente',  color: '#2A6E5C' },
  3: { label: '3 · Revisar',          color: '#8A9590' },
  2: { label: '2 · No prioritario',   color: '#C97A52' },
  1: { label: '1 · Excluido',         color: '#FF6B35' },
  0: { label: '0 · Fuera de rango',   color: '#5B6963' },
};

@Component({
  standalone: true,
  selector: 'app-donut-chart',
  imports: [NgxEchartsDirective],
  template: `
    <div echarts [options]="options()" [autoResize]="true" class="w-full h-[280px]"></div>
  `,
})
export class DonutChartComponent {
  papers = input.required<PaperSummary[]>();

  options = computed<EChartsCoreOption>(() => {
    const buckets: Record<number, number> = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    for (const p of this.papers()) {
      buckets[p.score_final] = (buckets[p.score_final] || 0) + 1;
    }
    const data = Object.entries(buckets)
      .filter(([_, v]) => v > 0)
      .map(([k, v]) => ({
        name: SCORE_META[+k].label,
        value: v,
        itemStyle: { color: SCORE_META[+k].color },
      }));

    return {
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c} papers ({d}%)' },
      legend: {
        orient: 'vertical',
        right: 0,
        top: 'middle',
        textStyle: { fontFamily: 'JetBrains Mono', fontSize: 11 },
        itemHeight: 8,
        itemWidth: 8,
      },
      series: [{
        type: 'pie',
        radius: ['55%', '78%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data,
      }],
    };
  });
}
