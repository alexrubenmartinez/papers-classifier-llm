import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Paper, PaperSummary, UploadResponse } from '../models';
import { API_BASE } from './api.config';

export type JustifyMode = 'none' | 'lazy' | 'auto';

@Injectable({ providedIn: 'root' })
export class PapersService {
  private http = inject(HttpClient);

  list(limit = 100, minScore = 0): Observable<PaperSummary[]> {
    const params = new HttpParams()
      .set('limit', String(limit))
      .set('min_score', String(minScore));
    return this.http.get<PaperSummary[]>(`${API_BASE}/papers`, { params });
  }

  get(paperId: string): Observable<Paper> {
    return this.http.get<Paper>(`${API_BASE}/papers/${paperId}`);
  }

  upload(file: File, justify: JustifyMode = 'none'): Observable<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    const params = new HttpParams().set('justify', justify);
    return this.http.post<UploadResponse>(`${API_BASE}/papers`, form, { params });
  }
}
