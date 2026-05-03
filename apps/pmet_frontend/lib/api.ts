import axios from 'axios';
import { TaskCreate, TaskResponse, TaskListResponse, UploadResponse, EstimatePayload, EstimateResponse, TaskProgress } from './types';

export interface AdminSettings {
  notify_on_submit: boolean;
  notify_user_on_start: boolean;
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

  me: async (): Promise<{ is_admin: boolean }> => {
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
};

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
};

export const fileApi = {
  upload: async (
    file: File,
    fileType: string,
    taskId?: string,
    onProgress?: (pct: number) => void
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_type', fileType);
    if (taskId) formData.append('task_id', taskId);

    const response = await api.post('/api/files/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress
        ? (e) => onProgress(Math.round((e.loaded / (e.total || e.loaded || 1)) * 100))
        : undefined,
    });
    return response.data;
  },

  uploadMultiple: async (files: File[], taskId?: string): Promise<{ files: UploadResponse[] }> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    if (taskId) formData.append('task_id', taskId);

    const response = await api.post('/api/files/upload-multiple', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteUpload: async (path: string): Promise<void> => {
    await api.delete('/api/files/upload', { params: { path } });
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
