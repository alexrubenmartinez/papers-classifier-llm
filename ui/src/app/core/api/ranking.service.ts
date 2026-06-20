import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { PaperSummary } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class RankingService {
  private http = inject(HttpClient);

  top(n = 10): Observable<PaperSummary[]> {
    const params = new HttpParams().set('top', String(n));
    return this.http.get<PaperSummary[]>(`${API_BASE}/ranking`, { params });
  }
}
