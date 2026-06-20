import { Injectable, signal, effect } from '@angular/core';

type Theme = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly KEY = 'theme';
  private _theme = signal<Theme>(this.resolveInitial());
  theme = this._theme.asReadonly();

  constructor() {
    // Reflect signal → DOM + localStorage every change
    effect(() => {
      const t = this._theme();
      const root = document.documentElement;
      if (t === 'dark') root.classList.add('dark');
      else root.classList.remove('dark');
      try { localStorage.setItem(this.KEY, t); } catch {}
    });

    // Respect OS-level changes only when user hasn't picked manually
    try {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      mq.addEventListener('change', e => {
        if (!localStorage.getItem(this.KEY)) {
          this._theme.set(e.matches ? 'dark' : 'light');
        }
      });
    } catch {}
  }

  toggle(): void {
    this._theme.update(t => (t === 'dark' ? 'light' : 'dark'));
  }

  set(t: Theme): void {
    this._theme.set(t);
  }

  private resolveInitial(): Theme {
    try {
      const stored = localStorage.getItem(this.KEY) as Theme | null;
      if (stored === 'dark' || stored === 'light') return stored;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  }
}
