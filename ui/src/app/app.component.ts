import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { GlowBackgroundComponent } from './shared/ui/glow-background.component';
import { FooterComponent } from './shared/layout/footer.component';
import { HeaderComponent } from './shared/layout/header.component';
import { ToastContainerComponent } from './shared/ui/toast-container.component';

@Component({
  standalone: true,
  selector: 'app-root',
  imports: [RouterOutlet, HeaderComponent, FooterComponent, GlowBackgroundComponent, ToastContainerComponent],
  template: `
    <app-glow-background />
    <app-header />
    <app-toast-container />

    <main class="relative z-10 max-w-[1400px] mx-auto px-4 sm:px-8 pt-28 sm:pt-24 pb-12">
      <router-outlet />
    </main>

    <app-footer />
  `,
})
export class AppComponent {}
