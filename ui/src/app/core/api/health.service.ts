import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { HealthStatus } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class HealthService {
  private http = inject(HttpClient);

  health(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>(`${API_BASE}/health`);
  }
}
