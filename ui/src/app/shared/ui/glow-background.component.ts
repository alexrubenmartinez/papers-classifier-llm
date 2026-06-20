import { Component, OnInit, OnDestroy, signal, inject } from '@angular/core';
import { ThemeService } from '../../core/theme.service';

/**
 * Ambient mesh of blurred blobs that float slowly behind everything.
 * Two color schemes — light (ember + jade + bone) and dark (mint + coral + violet).
 * The blobs translate with the scroll position for a subtle parallax effect.
 */
@Component({
  standalone: true,
  selector: 'app-glow-background',
  template: `
    <div class="ambient" aria-hidden="true">
      @if (theme.theme() === 'dark') {
        <div class="ambient-blob"
             style="width:520px;height:520px;left:-160px;top:-180px;background:radial-gradient(circle, #A7F3D0 0%, transparent 70%);"
             [style.animationDelay]="'0s'"></div>
        <div class="ambient-blob"
             style="width:480px;height:480px;right:-140px;top:35vh;background:radial-gradient(circle, #FF8C5A 0%, transparent 70%);"
             [style.animationDelay]="'-8s'"></div>
        <div class="ambient-blob"
             style="width:600px;height:600px;left:30vw;bottom:-220px;background:radial-gradient(circle, #7C3AED 0%, transparent 70%);"
             [style.animationDelay]="'-14s'"></div>
      } @else {
        <div class="ambient-blob"
             style="width:520px;height:520px;left:-160px;top:-180px;background:radial-gradient(circle, #FF6B35 0%, transparent 70%);"
             [style.animationDelay]="'0s'"></div>
        <div class="ambient-blob"
             style="width:480px;height:480px;right:-140px;top:35vh;background:radial-gradient(circle, #1F4438 0%, transparent 70%);"
             [style.animationDelay]="'-8s'"></div>
        <div class="ambient-blob"
             style="width:600px;height:600px;left:30vw;bottom:-220px;background:radial-gradient(circle, #F2E8DC 0%, transparent 70%);"
             [style.animationDelay]="'-14s'"></div>
      }
    </div>
    <div class="noise" aria-hidden="true"></div>
  `,
})
export class GlowBackgroundComponent {
  theme = inject(ThemeService);
}
