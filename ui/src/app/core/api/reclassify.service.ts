import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ReclassifyResponse } from '../models';
import { API_BASE } from './api.config';

export type ReclassifyJustifyMode = 'none' | 'gold_only' | 'all';

@Injectable({ providedIn: 'root' })
export class ReclassifyService {
  private http = inject(HttpClient);

  run(opts: { reextract?: boolean; justify?: ReclassifyJustifyMode } = {}): Observable<ReclassifyResponse> {
    const params = new HttpParams()
      .set('reextract', String(opts.reextract ?? false))
      .set('justify', opts.justify ?? 'none');
    return this.http.post<ReclassifyResponse>(`${API_BASE}/reclassify`, null, { params });
  }
}
