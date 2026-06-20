import { Component, Input } from '@angular/core';

@Component({
  standalone: true,
  selector: 'app-tag',
  template: `
    <span class="inline-flex items-center font-mono text-[10px] uppercase tracking-[0.14em] px-2.5 py-1 rounded-full border border-line-2 text-ink-2">
      <span class="text-ink-3 mr-1">·</span>{{ label }}
    </span>
  `,
})
export class TagComponent {
  @Input() label = '';
}
