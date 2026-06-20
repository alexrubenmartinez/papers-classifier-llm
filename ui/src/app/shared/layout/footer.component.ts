import { Component } from '@angular/core';

@Component({
  standalone: true,
  selector: 'app-footer',
  template: `
    <footer class="relative z-10 mt-24 sm:mt-32 px-4 sm:px-8">
      <div class="max-w-[1400px] mx-auto glass rounded-[40px] p-8 sm:p-14">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-12">

          <!-- Identity -->
          <div class="col-span-2 sm:col-span-1">
            <p class="digit-display text-7xl text-ink leading-none mb-4">Ø1</p>
            <p class="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-2">
              Examen · Group · One
            </p>
            <p class="font-mono text-[10px] tracking-[0.14em] text-ink-3 mt-1">
              BD avanzadas / 2026-I
            </p>
          </div>

          <!-- Pipeline -->
          <div>
            <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-4">// pipeline</p>
            <ul class="space-y-2 text-[13px] text-ink-2">
              <li><span class="font-mono text-ink-3">1.</span> &nbsp;PyMuPDF · metadata</li>
              <li><span class="font-mono text-ink-3">2.</span> &nbsp;SBERT · embeddings</li>
              <li><span class="font-mono text-ink-3">3.</span> &nbsp;TF-IDF + keywords</li>
              <li><span class="font-mono text-ink-3">4.</span> &nbsp;Ollama · justificación</li>
            </ul>
          </div>

          <!-- Endpoints -->
          <div>
            <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-4">// endpoints</p>
            <ul class="space-y-2 text-[13px] text-ink-2 font-mono">
              <li class="truncate">examen-api<span class="text-ink-3">.group-one</span></li>
              <li class="truncate">examen-ui<span class="text-ink-3">.group-one</span></li>
              <li class="truncate">ollama-api<span class="text-ink-3">.group-one</span></li>
              <li class="truncate">minio<span class="text-ink-3">.group-one</span></li>
            </ul>
          </div>

          <!-- Nota -->
          <div>
            <p class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 mb-4">// nota</p>
            <p class="text-[13px] leading-relaxed text-ink-2">
              Clasificar 2000 papers no es <span class="font-display-it text-ember">magia</span>: es geometría sobre embeddings, un poco de TF-IDF, y la disciplina de medir antes de cambiar.
            </p>
          </div>
        </div>

        <div class="mt-12 pt-6 border-t border-line-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-[11px] font-mono text-ink-3">
          <span>Examen take-home · Bases de datos avanzados y big data · 2026-I</span>
          <span class="flex items-center gap-3">
            <span class="w-1.5 h-1.5 rounded-full bg-jade inline-block animate-pulse"></span>
            <span>api · live</span>
          </span>
        </div>
      </div>
      <div class="h-6"></div>
    </footer>
  `,
})
export class FooterComponent {}
