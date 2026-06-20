import { Component, input, output, signal } from '@angular/core';

/**
 * Editor de keywords como chips. Tipea + enter (o coma) para agregar.
 * Click en × para borrar. Tambien acepta paste con keywords separados
 * por comas, saltos de linea o ;.
 */
@Component({
  standalone: true,
  selector: 'app-keyword-chips',
  template: `
    <div class="space-y-2">
      <div class="flex flex-wrap gap-1.5 p-3 rounded-2xl bg-paper-2/60 border border-line-2 min-h-[80px]">
        @for (kw of keywords(); track kw; let i = $index) {
          <span class="inline-flex items-center gap-1.5 rounded-full bg-jade/15 border border-jade/30 text-jade px-2.5 py-1 text-[12px] font-mono">
            {{ kw }}
            <button (click)="removeAt(i)" class="text-jade/70 hover:text-ember text-[13px] leading-none" aria-label="Borrar">×</button>
          </span>
        }
        <input #inp
               type="text"
               [value]="draft()"
               (input)="draft.set(inp.value)"
               (keydown.enter)="commit($event)"
               (keydown.comma)="commit($event)"
               (keydown.semicolon)="commit($event)"
               (keydown.backspace)="onBackspace($event)"
               (paste)="onPaste($event)"
               (blur)="commitOnBlur()"
               [placeholder]="placeholder()"
               class="flex-1 min-w-[140px] bg-transparent outline-none text-[13px] py-1 font-mono">
      </div>
      <div class="flex items-center justify-between font-mono text-[10px] text-ink-3">
        <span>{{ keywords().length }} palabras clave</span>
        @if (keywords().length > 0) {
          <button (click)="clearAll()" class="hover:text-ember">Borrar todo</button>
        }
      </div>
    </div>
  `,
})
export class KeywordChipsComponent {
  keywords = input.required<string[]>();
  placeholder = input<string>('escribe y enter (o paste con comas)…');

  changed = output<string[]>();
  draft = signal('');

  commit(ev: Event) {
    ev.preventDefault();
    const v = this.draft().trim().replace(/[,;]+$/, '');
    if (!v) return;
    this.append([v]);
    this.draft.set('');
  }

  commitOnBlur() {
    const v = this.draft().trim().replace(/[,;]+$/, '');
    if (!v) return;
    this.append([v]);
    this.draft.set('');
  }

  onBackspace(ev: Event) {
    if (this.draft().length === 0 && this.keywords().length > 0) {
      ev.preventDefault();
      this.removeAt(this.keywords().length - 1);
    }
  }

  onPaste(ev: ClipboardEvent) {
    const text = ev.clipboardData?.getData('text');
    if (!text) return;
    const parts = text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) {
      ev.preventDefault();
      this.append(parts);
      this.draft.set('');
    }
  }

  removeAt(i: number) {
    const next = [...this.keywords()];
    next.splice(i, 1);
    this.changed.emit(next);
  }

  clearAll() {
    this.changed.emit([]);
  }

  private append(items: string[]) {
    const existing = new Set(this.keywords().map((s) => s.toLowerCase()));
    const fresh: string[] = [];
    for (const it of items) {
      const norm = it.trim();
      if (norm && !existing.has(norm.toLowerCase())) {
        fresh.push(norm);
        existing.add(norm.toLowerCase());
      }
    }
    if (fresh.length) this.changed.emit([...this.keywords(), ...fresh]);
  }
}
