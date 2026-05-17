import axios from 'axios';
import { TaskCreate, TaskResponse, TaskListResponse, UploadResponse, EstimatePayload, EstimateResponse, TaskProgress } from './types';

export interface AdminSettings {
  notify_on_submit: boolean;
  notify_user_on_start: boolean;
  submissions_paused: boolean;
  admin_notify_email: string;
  minhash_threshold: number | null;
  result_retention_days: number | null;
}

export interface AdminMeResponse {
  is_admin: boolean;
  submissions_paused: boolean;
}

export interface AdminTrendPoint {
  date: string;
  submitted: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface AdminRuntimeStats {
  count: number;
  p50: number | null;
  p95: number | null;
  samples: number[];
}

export interface AdminTopError {
  message: string;
  count: number;
}

export interface AdminStatsResponse {
  range_days: number;
  submit_trend: AdminTrendPoint[];
  status_distribution: Record<string, number>;
  runtime_by_mode: Record<string, AdminRuntimeStats>;
  top_errors: AdminTopError[];
}

// Empty string = same-origin. In docker/nginx deployment the app is served on
// :80 and nginx proxies /api/* to the backend. In local dev, set
// NEXT_PUBLIC_API_URL=http://localhost:8000 when frontend runs on :3000.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // Admin auth uses an httpOnly cookie set by /api/admin/login. axios needs
  // withCredentials=true to send cookies on subsequent same-origin requests
  // when the dev server proxies via nginx.
  withCredentials: true,
});

export const taskApi = {
  create: async (task: TaskCreate): Promise<TaskResponse> => {
    const response = await api.post('/api/tasks', task);
    return response.data;
  },

  get: async (taskId: string): Promise<TaskResponse> => {
    const response = await api.get(`/api/tasks/${taskId}`);
    return response.data;
  },

  list: async (
    filter: { email?: string; task_id?: string } = {},
    limit = 50,
    offset = 0,
  ): Promise<TaskListResponse> => {
    const params = new URLSearchParams();
    if (filter.email) params.append('email', filter.email);
    if (filter.task_id) params.append('task_id', filter.task_id);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    const response = await api.get(`/api/tasks?${params.toString()}`);
    return response.data;
  },

  downloadResult: (taskId: string): string => {
    return `${API_URL}/api/tasks/${taskId}/result`;
  },

  cancel: async (taskId: string, reason?: string): Promise<{ ok: boolean; killed_pids: number[] }> => {
    const response = await api.post(`/api/tasks/${taskId}/cancel`, { reason });
    return response.data;
  },

  estimate: async (
    payload: EstimatePayload,
    signal?: AbortSignal,
  ): Promise<EstimateResponse> => {
    const response = await api.post('/api/tasks/estimate', payload, { signal });
    return response.data;
  },

  progress: async (taskId: string): Promise<TaskProgress> => {
    const response = await api.get(`/api/tasks/${taskId}/progress`);
    return response.data;
  },
};

export const adminApi = {
  login: async (token: string): Promise<{ ok: boolean }> => {
    const response = await api.post('/api/admin/login', { token });
    return response.data;
  },

  logout: async (): Promise<{ ok: boolean }> => {
    const response = await api.post('/api/admin/logout');
    return response.data;
  },

  me: async (): Promise<AdminMeResponse> => {
    const response = await api.get('/api/admin/me');
    return response.data;
  },

  getSettings: async (): Promise<AdminSettings> => {
    const response = await api.get('/api/admin/settings');
    return response.data;
  },

  updateSettings: async (
    settings: AdminSettings,
  ): Promise<AdminSettings> => {
    const response = await api.put('/api/admin/settings', settings);
    return response.data;
  },

  stats: async (days: number): Promise<AdminStatsResponse> => {
    const response = await api.get(`/api/admin/stats?days=${days}`);
    return response.data;
  },

  audit: async (params?: { n?: number; category?: 'admin' | 'mail' }): Promise<{ records: AdminAuditRecord[] }> => {
    const q = new URLSearchParams();
    if (params?.n) q.set('n', String(params.n));
    if (params?.category) q.set('category', params.category);
    const qs = q.toString();
    const response = await api.get(`/api/admin/audit${qs ? '?' + qs : ''}`);
    return response.data;
  },

  rotateToken: async (): Promise<{ token: string }> => {
    const response = await api.post('/api/admin/rotate-token');
    return response.data;
  },

  cleanupPreview: async (): Promise<{ retention_days: number; eligible: number }> => {
    const response = await api.get('/api/admin/cleanup/preview');
    return response.data;
  },

  cleanupRun: async (): Promise<CleanupReport> => {
    const response = await api.post('/api/admin/cleanup/run');
    return response.data;
  },

  health: async (): Promise<{ checks: HealthCheck[] }> => {
    const response = await api.get('/api/admin/health/check');
    return response.data;
  },

  taskDebug: async (taskId: string): Promise<{ task_id: string; meta: Record<string, unknown>; stderr_tail: string[] | null }> => {
    const response = await api.get(`/api/admin/task/${taskId}/debug`);
    return response.data;
  },

  taskSetNote: async (taskId: string, note: string | null): Promise<{ task_id: string; admin_note: string | null }> => {
    const response = await api.put(`/api/admin/task/${taskId}/note`, { note });
    return response.data;
  },

  taskRerun: async (taskId: string): Promise<{ task_id: string; rerun_of: string }> => {
    const response = await api.post(`/api/admin/task/${taskId}/rerun`);
    return response.data;
  },
};

export interface HealthCheck {
  name: 'smtp' | 'redis' | 'disk' | 'tasks_dir' | 'configure_dir' | string;
  status: 'ok' | 'warn' | 'fail';
  detail: Record<string, unknown>;
}

export interface CleanupReport {
  retention_days: number;
  skipped?: boolean;
  reason?: string;
  candidates?: number;
  removed_dirs: number;
  removed_zips: number;
  removed_metas: number;
  errors: string[];
}

export interface AdminAuditRecord {
  ts: string;
  category: 'admin' | 'mail' | string;
  action: string;
  ok: boolean;
  ip: string | null;
  target: string | null;
  detail: unknown;
}

export const resultsApi = {
  get: async (taskId: string, params?: {
    cluster?: string;
    p_adj_max?: number;
    limit?: number;
    offset?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.cluster) query.append('cluster', params.cluster);
    if (params?.p_adj_max !== undefined) query.append('p_adj_max', String(params.p_adj_max));
    if (params?.limit !== undefined) query.append('limit', String(params.limit));
    if (params?.offset !== undefined) query.append('offset', String(params.offset));
    const qs = query.toString();
    const response = await api.get(`/api/results/${taskId}${qs ? '?' + qs : ''}`);
    return response.data;
  },

  summary: async (taskId: string) => {
    const response = await api.get(`/api/results/${taskId}/summary`);
    return response.data;
  },

  genesUsed: async (taskId: string) => {
    const response = await api.get(`/api/results/${taskId}/genes-used`);
    return response.data;
  },

  // Raw motif_output.txt as text, no filtering, no row cap. Used by
  // the /visualize page when opened with ?task=<id> so it parses the
  // same bytes the upload-zone path would — keeps the two flows in
  // perfect sync. The paginated `get()` above stays for the task
  // detail page's table view, where pagination is what you want.
  raw: async (taskId: string): Promise<string> => {
    const response = await api.get(`/api/results/${taskId}/raw`, {
      responseType: 'text',
      transformResponse: (v) => v,
    });
    return response.data as string;
  },
};

export interface IndexingFixedParams {
  promoter_length?: number;
  promoter_num?: number;
  max_match?: number;
  fimo_threshold?: number;
  ic_threshold?: number;
  utr5?: string;
  promoters_overlap?: string;
}

export interface IndexingEntry {
  value: string;
  species: string;
  motif_db: string;
  label: string;
  fixed_params?: IndexingFixedParams;
}

export interface IndexingSpeciesDetail {
  name: string;
  humanized: string;
  description: string | null;
  genome_name: string | null;
  genome_link: string | null;
  annotation_name: string | null;
  annotation_link: string | null;
  gene_count: number;
  gene_sample: string[];
}

export interface IndexingMotifDbDetail {
  name: string;
  humanized: string;
  source_link: string | null;
  motif_count: number;
  motif_sample: string[];
}

export interface GenomeCatalogEntry {
  name: string;
  humanized: string;
  description: string | null;
  genome_name: string | null;
  genome_link: string | null;
  annotation_name: string | null;
  annotation_link: string | null;
}

export interface MotifDbCatalogEntry {
  name: string;
  humanized: string;
  source_link: string | null;
  local_file: { filename: string; size_bytes: number } | null;
}

export const indexingApi = {
  list: async (): Promise<{ entries: IndexingEntry[] }> => {
    const response = await api.get('/api/indexing');
    return response.data;
  },

  speciesDetail: async (species: string): Promise<{ species: IndexingSpeciesDetail }> => {
    const response = await api.get(`/api/indexing/${encodeURIComponent(species)}`);
    return response.data;
  },

  motifDbDetail: async (species: string, motifDb: string): Promise<{ motif_db: IndexingMotifDbDetail }> => {
    const response = await api.get(
      `/api/indexing/${encodeURIComponent(species)}/${encodeURIComponent(motifDb)}`,
    );
    return response.data;
  },

  genomes: async (): Promise<{ species: GenomeCatalogEntry[] }> => {
    const response = await api.get('/api/indexing/genomes');
    return response.data;
  },

  motifDatabases: async (): Promise<{ databases: MotifDbCatalogEntry[] }> => {
    const response = await api.get('/api/indexing/motif-databases');
    return response.data;
  },
};

export interface IssueSessionResponse {
  session_id: string;
  session_token: string;
  expires_in: number;
}

export const fileApi = {
  // Hand the caller a fresh session_id + session_token pair. Required
  // by DELETE /upload now that PMET is on a public domain, and also
  // passed to /use-example so the submit flow has one consistent
  // server-issued session boundary. Frontend calls this once on
  // submit-page mount.
  issueSession: async (): Promise<IssueSessionResponse> => {
    const response = await api.post('/api/files/issue-session');
    return response.data;
  },

  upload: async (
    file: File,
    fileType: string,
    taskId: string,
    sessionToken: string,
    onProgress?: (pct: number) => void
  ): Promise<UploadResponse> => {
    // Session id + token live in headers so the backend can reject
    // invalid callers before parsing a potentially large multipart body.
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_type', fileType);

    const response = await api.post('/api/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-PMET-Session-Id': taskId,
        'X-PMET-Session-Token': sessionToken,
      },
      onUploadProgress: onProgress
        ? (e) => onProgress(Math.round((e.loaded / (e.total || e.loaded || 1)) * 100))
        : undefined,
    });
    return response.data;
  },

  // Server-side reference to a demo file under data/. Replaces the
  // wasteful "fetch 116 MB demo, repackage as Blob, repost 116 MB"
  // round-trip the legacy `Use Example` flow had to do for the big
  // FASTA / GFF3 inputs, without creating upload/ copies or symlinks.
  useExample: async (
    taskId: string,
    mode: string,
    slot: string,
    sessionToken: string,
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('task_id', taskId);
    formData.append('mode', mode);
    formData.append('slot', slot);
    formData.append('session_token', sessionToken);
    const response = await api.post('/api/files/use-example', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteUpload: async (path: string, sessionToken?: string): Promise<void> => {
    // sessionToken is optional in the type for legacy/test callers, but
    // the backend now 401s without it on a session-bound path. Send it
    // as a header, not a query parameter, so it does not end up in URLs
    // or access logs.
    await api.delete('/api/files/upload', {
      params: { path },
      headers: sessionToken ? { 'X-PMET-Session-Token': sessionToken } : undefined,
    });
  },

  // Size-capped text preview of a user-uploaded file (genes / fasta /
  // gff3 / meme). Backend rejects anything outside the task's own
  // upload dir, so passing a slot whose path points at server-side
  // reference data returns 403 — caller should gate the UI on the
  // path's location, not on a preview attempt.
  previewUpload: async (
    taskId: string,
    slot: 'genes' | 'fasta' | 'gff3' | 'meme'
  ): Promise<FilePreview> => {
    const response = await api.get(`/api/files/preview/${taskId}/${slot}`);
    return response.data;
  },
};

export interface FilePreview {
  filename: string;
  size_bytes: number;
  content: string;
  truncated: boolean;
  line_count: number | null;
}

export default api;
