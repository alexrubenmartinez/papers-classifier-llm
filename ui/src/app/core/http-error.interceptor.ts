import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { ToastService } from './toast/toast.service';

/**
 * Captura cualquier error HTTP no manejado por el caller y lo muestra como toast.
 * El error se sigue propagando al observable original para que el componente
 * caller pueda hacer su propio handling local si lo necesita.
 */
export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const detail =
        (typeof err.error === 'object' && err.error?.detail) ||
        (typeof err.error === 'string' && err.error) ||
        err.message ||
        `HTTP ${err.status}`;
      const status = err.status ? `${err.status} · ` : '';
      toast.error(`${status}${detail}`);
      return throwError(() => err);
    }),
  );
};
