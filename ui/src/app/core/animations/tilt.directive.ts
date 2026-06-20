import { Directive, ElementRef, HostListener, Input, inject } from '@angular/core';

/**
 * Apple-flavoured 3D tilt on hover. Sets CSS variables --tx/--ty consumed by
 * the .tilt utility class. No deps, GPU-driven.
 *
 * Usage: <div appTilt [tiltMax]="8" class="tilt"> … </div>
 */
@Directive({ standalone: true, selector: '[appTilt]' })
export class TiltDirective {
  private el = inject(ElementRef<HTMLElement>);
  @Input() tiltMax = 6;
  private reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  @HostListener('mousemove', ['$event'])
  onMove(e: MouseEvent) {
    if (this.reduced) return;
    const node = this.el.nativeElement;
    const rect = node.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const tx = (0.5 - y) * this.tiltMax;
    const ty = (x - 0.5) * this.tiltMax;
    node.style.setProperty('--tx', `${tx}deg`);
    node.style.setProperty('--ty', `${ty}deg`);
  }

  @HostListener('mouseleave')
  onLeave() {
    const node = this.el.nativeElement;
    node.style.setProperty('--tx', '0deg');
    node.style.setProperty('--ty', '0deg');
  }
}
