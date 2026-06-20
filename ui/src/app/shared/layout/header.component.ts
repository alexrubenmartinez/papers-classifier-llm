import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { ThemeService } from '../../core/theme.service';

@Component({
  standalone: true,
  selector: 'app-header',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <header class="fixed top-3 left-3 right-3 sm:top-4 sm:left-4 sm:right-4 z-50">
      <div class="glass rounded-full px-3 sm:px-4 py-2.5 flex items-center justify-between gap-3">

        <!-- Logo -->
        <a routerLink="/" class="flex items-center gap-2.5 group pl-1.5">
          <span class="digit-display text-2xl text-ink select-none transition-transform duration-500 group-hover:rotate-[-6deg]">Ø1</span>
          <span class="hidden sm:flex flex-col leading-none mt-1">
            <span class="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-2">Examen · BD avanzadas</span>
            <span class="font-mono text-[9px] tracking-[0.14em] text-ink-3 mt-1">UNMSM / 2026-I</span>
          </span>
        </a>

        <!-- Nav: pills (desktop) -->
        <nav class="hidden lg:flex items-center gap-1">
          <a routerLink="/" routerLinkActive="!bg-ink !text-paper" [routerLinkActiveOptions]="{exact: true}" class="pill">Dashboard</a>
          <a routerLink="/papers" routerLinkActive="!bg-ink !text-paper" class="pill">Papers</a>
          <a routerLink="/ranking" routerLinkActive="!bg-ink !text-paper" class="pill">Ranking</a>
          <a routerLink="/config" routerLinkActive="!bg-ink !text-paper" class="pill">Tema</a>
          <a routerLink="/upload" routerLinkActive="!bg-ink !text-paper" class="pill">Subir</a>
          <a routerLink="/reclassify" routerLinkActive="!bg-ink !text-paper" class="pill">Reclasificar</a>
          <a routerLink="/jobs" routerLinkActive="!bg-ink !text-paper" class="pill">
            <span class="w-1.5 h-1.5 rounded-full bg-jade inline-block animate-pulse"></span>
            Jobs
          </a>
          <a routerLink="/chat" routerLinkActive="!bg-ink !text-paper" class="pill">Chat</a>
        </nav>

        <!-- Theme toggle -->
        <div class="flex items-center gap-1.5">
          <button (click)="theme.toggle()"
                  [attr.aria-label]="theme.theme() === 'dark' ? 'Cambiar a modo día' : 'Cambiar a modo noche'"
                  class="relative w-[88px] h-9 rounded-full border-line-2 border bg-paper-2/40 backdrop-blur-md overflow-hidden text-[10px] font-mono uppercase tracking-[0.14em] hidden sm:flex">
            <span class="absolute inset-0 grid grid-cols-2 items-center">
              <span class="text-center transition-colors duration-300"
                    [class.text-ink]="theme.theme() === 'light'"
                    [class.text-ink-3]="theme.theme() === 'dark'">Día</span>
              <span class="text-center transition-colors duration-300"
                    [class.text-ink]="theme.theme() === 'dark'"
                    [class.text-ink-3]="theme.theme() === 'light'">Noche</span>
            </span>
            <span class="absolute top-[3px] bottom-[3px] w-[42px] rounded-full bg-jade transition-all duration-500 ease-spring"
                  [style.left]="theme.theme() === 'dark' ? 'calc(100% - 45px)' : '3px'"></span>
          </button>
        </div>
      </div>

      <!-- Mobile nav strip (overflow scroll) -->
      <div class="lg:hidden mt-2 flex gap-1 overflow-x-auto px-2 pb-1">
        <a routerLink="/" routerLinkActive="!bg-ink !text-paper" [routerLinkActiveOptions]="{exact: true}" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Dashboard</a>
        <a routerLink="/papers" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Papers</a>
        <a routerLink="/ranking" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Ranking</a>
        <a routerLink="/config" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Tema</a>
        <a routerLink="/upload" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Subir</a>
        <a routerLink="/reclassify" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Reclasificar</a>
        <a routerLink="/jobs" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Jobs</a>
        <a routerLink="/chat" routerLinkActive="!bg-ink !text-paper" class="pill !text-[10px] !py-1.5 !px-3 whitespace-nowrap">Chat</a>
      </div>
    </header>
  `,
})
export class HeaderComponent {
  theme = inject(ThemeService);
}
