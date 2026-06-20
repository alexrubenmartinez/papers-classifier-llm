import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../core/api/chat.service';
import { ChatMessage } from '../../core/models';

@Component({
  standalone: true,
  selector: 'app-chat',
  imports: [FormsModule],
  template: `
    <section class="space-y-6 pt-6 max-w-3xl">
      <header>
        <p class="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">chat</p>
        <h1 class="font-display text-4xl text-ink">Hablar con Ollama</h1>
        <p class="text-ink-2 text-[14px] mt-2">qwen2.5:1.5b en CPU. Cada respuesta toma ~5-20s warm.</p>
      </header>

      <div class="glass rounded-3xl p-6 sm:p-8 space-y-5">
        <div class="space-y-3 min-h-[200px] max-h-[500px] overflow-y-auto pr-2">
          @for (msg of messages(); track $index) {
            <div class="flex {{ msg.role === 'user' ? 'justify-end' : 'justify-start' }}">
              <div class="max-w-[80%] rounded-2xl px-4 py-2.5 text-[14px] {{ msg.role === 'user' ? 'bg-jade text-paper' : 'bg-paper-2 text-ink' }}">
                <p class="whitespace-pre-wrap">{{ msg.content }}</p>
              </div>
            </div>
          } @empty {
            <p class="text-ink-3 text-sm text-center py-8">Sin mensajes. Envía uno abajo para empezar.</p>
          }
          @if (waiting()) {
            <p class="font-mono text-[11px] text-ink-3 animate-pulse">qwen2.5:1.5b está pensando…</p>
          }
        </div>

        <div class="flex gap-2 pt-4 border-t border-line-2">
          <input type="text" [(ngModel)]="input" (keydown.enter)="send()"
                 placeholder="Escribí algo y enter…"
                 class="flex-1 bg-paper-2 border border-line-2 rounded-full px-4 py-2.5 text-[14px]">
          <button (click)="send()" [disabled]="!input.trim() || waiting()"
                  class="pill !bg-ink !text-paper disabled:opacity-30">Enviar</button>
        </div>
      </div>
    </section>
  `,
})
export class ChatPage {
  private chatSvc = inject(ChatService);
  messages = signal<ChatMessage[]>([]);
  input = '';
  waiting = signal(false);

  send() {
    const text = this.input.trim();
    if (!text || this.waiting()) return;
    const userMsg: ChatMessage = { role: 'user', content: text };
    this.messages.update((m) => [...m, userMsg]);
    this.input = '';
    this.waiting.set(true);
    this.chatSvc.send({ messages: this.messages() }).subscribe({
      next: (r) => {
        this.messages.update((m) => [...m, { role: 'assistant', content: r.message }]);
        this.waiting.set(false);
      },
      error: (err) => {
        this.messages.update((m) => [...m, { role: 'assistant', content: `[error: ${err.message || err}]` }]);
        this.waiting.set(false);
      },
    });
  }
}
