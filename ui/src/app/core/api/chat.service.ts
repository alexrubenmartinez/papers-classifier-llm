import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ChatRequest, ChatResponse } from '../models';
import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private http = inject(HttpClient);

  send(req: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${API_BASE}/chat`, req);
  }
}
