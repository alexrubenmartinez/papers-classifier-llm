import { Injectable, Signal, signal } from '@angular/core';

export type ToastSeverity = 'info' | 'success' | 'error';

export interface Toast {
  id: string;
  message: string;
  severity: ToastSeverity;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private _items = signal<Toast[]>([]);
  items: Signal<Toast[]> = this._items.asReadonly();

  show(message: string, severity: ToastSeverity = 'info', durationMs = 5000): void {
    const id = Math.random().toString(36).slice(2, 10);
    this._items.update((arr) => [...arr, { id, message, severity }]);
    if (durationMs > 0) setTimeout(() => this.dismiss(id), durationMs);
  }

  error(message: string): void { this.show(message, 'error', 7000); }
  success(message: string): void { this.show(message, 'success', 4000); }
  info(message: string): void { this.show(message, 'info', 5000); }

  dismiss(id: string): void {
    this._items.update((arr) => arr.filter((t) => t.id !== id));
  }
}
