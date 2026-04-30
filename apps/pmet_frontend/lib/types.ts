export type AnalysisMode = 'promoters_pre' | 'promoters' | 'intervals';
export type TaskMode = AnalysisMode;
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface TaskCreate {
  email: string;
  mode: TaskMode;
  // Frontend-generated UUID reused for upload + task id.
  task_id?: string;
  ic_threshold: number;
  max_match: number;
  promoter_num: number;
  fimo_threshold: number;
  genes_file: string;
  promoter_length?: number;
  utr5?: string;
  promoters_overlap?: string;
  fasta_file?: string;
  gff3_file?: string;
  meme_file?: string;
  premade_index?: string;
}

export interface TaskResponse {
  task_id: string;
  status: TaskStatus;
  mode: TaskMode;
  email: string;
  result_link: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;

  // Submitted parameters (populated for any task; null for legacy records)
  ic_threshold?: number | null;
  max_match?: number | null;
  promoter_num?: number | null;
  fimo_threshold?: number | null;
  promoter_length?: number | null;
  utr5?: string | null;
  promoters_overlap?: string | null;

  // Input file paths relative to repo root
  genes_file?: string | null;
  fasta_file?: string | null;
  gff3_file?: string | null;
  meme_file?: string | null;
  premade_index?: string | null;

  // Current worker thread count (data/configure/cpu_configuration.txt)
  ncpu?: number | null;
}

export interface TaskListResponse {
  tasks: TaskResponse[];
  total: number;
}

export interface UploadResponse {
  filename: string;
  path: string;
  size: number;
}
