import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { JustifyBatchResponse, JustifyRequest, JustifyResponse } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class JustifyService {
  private http = inject(HttpClient);

  one(paperId: string): Observable<JustifyResponse> {
    return this.http.post<JustifyResponse>(`${API_BASE}/justify/${paperId}`, null);
  }

  batch(body: JustifyRequest): Observable<JustifyBatchResponse> {
    return this.http.post<JustifyBatchResponse>(`${API_BASE}/justify`, body);
  }
}
