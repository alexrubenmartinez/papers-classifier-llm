import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { JobStatus } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class JobsService {
  private http = inject(HttpClient);

  get(jobId: string): Observable<JobStatus> {
    return this.http.get<JobStatus>(`${API_BASE}/jobs/${jobId}`);
  }

  list(limit = 50): Observable<JobStatus[]> {
    const params = new HttpParams().set('limit', String(limit));
    return this.http.get<JobStatus[]>(`${API_BASE}/jobs`, { params });
  }
}
