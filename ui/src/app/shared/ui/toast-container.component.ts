import { Component, inject } from '@angular/core';
import { ToastService } from '../../core/toast/toast.service';

@Component({
  standalone: true,
  selector: 'app-toast-container',
  template: `
    <div class="fixed top-20 right-4 z-[200] space-y-2 max-w-sm pointer-events-none">
      @for (t of toast.items(); track t.id) {
        <div class="pointer-events-auto glass rounded-2xl px-4 py-3 border shadow-lg flex items-start gap-3 {{ borderClass(t.severity) }}"
             role="status">
          <span class="w-2 h-2 rounded-full mt-1.5 flex-shrink-0 {{ dotClass(t.severity) }}"></span>
          <p class="text-[13px] flex-1 {{ textClass(t.severity) }}">{{ t.message }}</p>
          <button (click)="toast.dismiss(t.id)" class="text-ink-3 hover:text-ink text-[16px] leading-none">×</button>
        </div>
      }
    </div>
  `,
})
export class ToastContainerComponent {
  toast = inject(ToastService);

  borderClass(s: 'info' | 'success' | 'error'): string {
    if (s === 'error') return 'border-ember/50';
    if (s === 'success') return 'border-jade/40';
    return 'border-line-2';
  }

  dotClass(s: 'info' | 'success' | 'error'): string {
    if (s === 'error') return 'bg-ember';
    if (s === 'success') return 'bg-jade';
    return 'bg-ink-3';
  }

  textClass(s: 'info' | 'success' | 'error'): string {
    if (s === 'error') return 'text-ember';
    return 'text-ink';
  }
}
