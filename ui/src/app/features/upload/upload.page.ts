import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { JustifyMode, PapersService } from '../../core/api/papers.service';

@Component({
  standalone: true,
  selector: 'app-upload',
  imports: [FormsModule],
  template: `
    <section class="space-y-6 pt-6 max-w-3xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">upload</p>
        <h1 class="font-display text-4xl text-ink">Subir PDF</h1>
      </header>

      <div class="glass rounded-3xl p-8 space-y-6">
        <!-- Dropzone -->
        <label class="block border-2 border-dashed border-line-2 rounded-3xl p-12 text-center cursor-pointer hover:border-jade transition-colors"
               (dragover)="$event.preventDefault()"
               (drop)="onDrop($event)">
          <input #fileInput type="file" accept=".pdf" hidden (change)="onFileSelected($event)">
          @if (file()) {
            <p class="font-mono text-[13px] text-jade">{{ file()!.name }}</p>
            <p class="font-mono text-[11px] text-ink-3 mt-1">{{ (file()!.size / 1024).toFixed(1) }} KB</p>
          } @else {
            <p class="text-ink-2">Arrastra un PDF aquí o haz click para elegir uno.</p>
            <p class="font-mono text-[11px] text-ink-3 mt-2">solo .pdf · hasta 32 MB</p>
          }
        </label>

        <!-- Modo justify -->
        <div class="space-y-2">
          <label class="block font-mono text-[10px] uppercase tracking-wider text-ink-3">modo de justificación</label>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            @for (mode of modes; track mode.value) {
              <label class="flex flex-col gap-1.5 p-4 rounded-2xl border cursor-pointer transition-colors"
                     [class.border-jade]="justify() === mode.value"
                     [class.bg-jade]="false"
                     [class.border-line-2]="justify() !== mode.value">
                <div class="flex items-center gap-2">
                  <input type="radio" name="justify" [value]="mode.value" [(ngModel)]="justifyValue"
                         (ngModelChange)="justify.set($event)"
                         class="accent-jade">
                  <span class="font-mono text-[12px] uppercase tracking-wider">{{ mode.value }}</span>
                </div>
                <p class="text-[12px] text-ink-2 leading-relaxed">{{ mode.desc }}</p>
                <p class="font-mono text-[10px] text-ink-3">{{ mode.cost }}</p>
              </label>
            }
          </div>
        </div>

        <!-- Botón -->
        <div class="flex justify-end">
          <button (click)="upload()" [disabled]="!file() || uploading()"
                  class="pill !bg-ink !text-paper disabled:opacity-30 disabled:cursor-not-allowed">
            {{ uploading() ? 'Subiendo…' : 'Subir y procesar' }}
          </button>
        </div>
      </div>
    </section>
  `,
})
export class UploadPage {
  private papersSvc = inject(PapersService);
  private router = inject(Router);

  file = signal<File | null>(null);
  justify = signal<JustifyMode>('none');
  justifyValue: JustifyMode = 'none';
  uploading = signal(false);

  modes: Array<{ value: JustifyMode; desc: string; cost: string }> = [
    { value: 'none', desc: 'Solo pipeline SBERT. La justificación queda en blanco.', cost: 'sin costo extra' },
    { value: 'lazy', desc: 'Pipeline ahora; justificación se genera cuando entres al detalle del paper.', cost: '~15s al pedirla' },
    { value: 'auto', desc: 'Pipeline + justificación con Ollama automática al terminar.', cost: '+15s al upload' },
  ];

  onFileSelected(ev: Event) {
    const input = ev.target as HTMLInputElement;
    this.file.set(input.files?.[0] || null);
  }

  onDrop(ev: DragEvent) {
    ev.preventDefault();
    const f = ev.dataTransfer?.files?.[0];
    if (f) this.file.set(f);
  }

  upload() {
    const f = this.file();
    if (!f) return;
    this.uploading.set(true);
    this.papersSvc.upload(f, this.justify()).subscribe({
      next: (r) => {
        this.uploading.set(false);
        this.router.navigate(['/jobs', r.job_id]);
      },
      error: () => this.uploading.set(false),
    });
  }
}
