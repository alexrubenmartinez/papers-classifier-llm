import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage) },
  { path: 'papers', loadComponent: () => import('./features/papers/papers-list.page').then((m) => m.PapersListPage) },
  { path: 'papers/:id', loadComponent: () => import('./features/papers/paper-detail.page').then((m) => m.PaperDetailPage) },
  { path: 'ranking', loadComponent: () => import('./features/ranking/ranking.page').then((m) => m.RankingPage) },
  { path: 'config', loadComponent: () => import('./features/config/config.page').then((m) => m.ConfigPage) },
  { path: 'upload', loadComponent: () => import('./features/upload/upload.page').then((m) => m.UploadPage) },
  { path: 'reclassify', loadComponent: () => import('./features/reclassify/reclassify.page').then((m) => m.ReclassifyPage) },
  { path: 'jobs', loadComponent: () => import('./features/jobs/jobs.page').then((m) => m.JobsPage) },
  { path: 'jobs/:id', loadComponent: () => import('./features/jobs/jobs.page').then((m) => m.JobsPage) },
  { path: 'chat', loadComponent: () => import('./features/chat/chat.page').then((m) => m.ChatPage) },
  { path: '**', redirectTo: '' },
];
