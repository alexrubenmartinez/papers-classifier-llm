import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { QueryConfig, QueryConfigUpdate } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private http = inject(HttpClient);

  get(): Observable<QueryConfig> {
    return this.http.get<QueryConfig>(`${API_BASE}/config`);
  }

  update(body: QueryConfigUpdate, reclassify = false): Observable<QueryConfig> {
    const params = new HttpParams().set('reclassify', String(reclassify));
    return this.http.put<QueryConfig>(`${API_BASE}/config`, body, { params });
  }
}
