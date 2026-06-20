import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withInMemoryScrolling } from '@angular/router';
import { provideEchartsCore } from 'ngx-echarts';

import { routes } from './app.routes';
import { httpErrorInterceptor } from './core/http-error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withInMemoryScrolling({ scrollPositionRestoration: 'top', anchorScrolling: 'enabled' })),
    provideHttpClient(withInterceptors([httpErrorInterceptor])),
    provideEchartsCore({ echarts: () => import('echarts') }),
  ],
};
