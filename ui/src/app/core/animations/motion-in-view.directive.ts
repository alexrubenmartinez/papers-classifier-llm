import { Directive, ElementRef, Input, AfterViewInit, OnDestroy, inject } from '@angular/core';
import { animate } from 'motion';

/**
 * Reveal an element when it enters the viewport.
 * - Respects prefers-reduced-motion.
 * - Spring-style ease.
 * - Optional vertical offset.
 */
@Directive({ standalone: true, selector: '[motionInView]' })
export class MotionInViewDirective implements AfterViewInit, OnDestroy {
  private el = inject(ElementRef<HTMLElement>);
  @Input() motionDelay = 0;
  @Input() motionY = 24;
  @Input() motionDuration = 0.8;
  private obs?: IntersectionObserver;

  ngAfterViewInit() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      this.el.nativeElement.style.opacity = '1';
      return;
    }
    this.el.nativeElement.style.opacity = '0';
    this.el.nativeElement.style.willChange = 'opacity, transform';
    this.obs = new IntersectionObserver(
      es => {
        for (const e of es) {
          if (e.isIntersecting) {
            animate(
              e.target as HTMLElement,
              { opacity: [0, 1], transform: [`translateY(${this.motionY}px)`, 'translateY(0)'] },
              { duration: this.motionDuration, delay: this.motionDelay, ease: [0.22, 1, 0.36, 1] as any },
            );
            this.obs?.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
    );
    this.obs.observe(this.el.nativeElement);
  }

  ngOnDestroy() {
    this.obs?.disconnect();
  }
}
