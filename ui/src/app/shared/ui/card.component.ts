import { Component } from '@angular/core';

/**
 * Glass primitive — the universal surface of the site.
 * Apply `.glass` directly when you need more control; this wraps content for the
 * default shape.
 */
@Component({
  standalone: true,
  selector: 'app-card',
  template: `
    <div class="glass">
      <ng-content></ng-content>
    </div>
  `,
})
export class CardComponent {}
