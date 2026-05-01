import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { TaskResponse } from './types';

interface TaskStore {
  currentTask: TaskResponse | null;
  tasks: TaskResponse[];
  loading: boolean;
  error: string | null;

  setCurrentTask: (task: TaskResponse | null) => void;
  setTasks: (tasks: TaskResponse[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  addTask: (task: TaskResponse) => void;
  updateTask: (taskId: string, updates: Partial<TaskResponse>) => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  currentTask: null,
  tasks: [],
  loading: false,
  error: null,

  setCurrentTask: (task) => set({ currentTask: task }),
  setTasks: (tasks) => set({ tasks }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  addTask: (task) => set((state) => ({ tasks: [task, ...state.tasks] })),
  updateTask: (taskId, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.task_id === taskId ? { ...t, ...updates } : t)),
      currentTask:
        state.currentTask?.task_id === taskId
          ? { ...state.currentTask, ...updates }
          : state.currentTask,
    })),
}));

type AnalysisMode = 'promoters_pre' | 'promoters' | 'intervals';

// Files / paths / species are kept by mode so a switch between tabs
// doesn't trample whichever picks belong to the other mode. Hoisted into
// the settings store (in-memory only — see partialize below) so they
// survive route changes too. The bug we're fixing: navigating /submit →
// /tasks → /submit unmounted the page and lost everything.
export interface ModeFiles {
  genes: File | null;
  fasta: File | null;
  gff3: File | null;
  meme: File | null;
  premade_index: string;
}
export interface ModePaths {
  genes: string;
  fasta: string;
  gff3: string;
  meme: string;
}

const emptyFiles: ModeFiles = { genes: null, fasta: null, gff3: null, meme: null, premade_index: '' };
const emptyPaths: ModePaths = { genes: '', fasta: '', gff3: '', meme: '' };

interface SettingsStore {
  mode: AnalysisMode;
  email: string;
  filesByMode: Record<AnalysisMode, ModeFiles>;
  pathsByMode: Record<AnalysisMode, ModePaths>;
  speciesByMode: Record<AnalysisMode, string>;
  setMode: (mode: AnalysisMode) => void;
  setEmail: (email: string) => void;
  updateFilesForMode: (mode: AnalysisMode, patch: Partial<ModeFiles>) => void;
  updatePathsForMode: (mode: AnalysisMode, patch: Partial<ModePaths>) => void;
  setSpeciesForMode: (mode: AnalysisMode, species: string) => void;
  resetSubmitForm: () => void;
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      mode: 'promoters_pre',
      email: '',
      filesByMode: {
        promoters_pre: { ...emptyFiles },
        promoters: { ...emptyFiles },
        intervals: { ...emptyFiles },
      },
      pathsByMode: {
        promoters_pre: { ...emptyPaths },
        promoters: { ...emptyPaths },
        intervals: { ...emptyPaths },
      },
      speciesByMode: { promoters_pre: '', promoters: '', intervals: '' },
      setMode: (mode) => set({ mode }),
      setEmail: (email) => set({ email }),
      updateFilesForMode: (mode, patch) =>
        set((state) => ({
          filesByMode: { ...state.filesByMode, [mode]: { ...state.filesByMode[mode], ...patch } },
        })),
      updatePathsForMode: (mode, patch) =>
        set((state) => ({
          pathsByMode: { ...state.pathsByMode, [mode]: { ...state.pathsByMode[mode], ...patch } },
        })),
      setSpeciesForMode: (mode, species) =>
        set((state) => ({
          speciesByMode: { ...state.speciesByMode, [mode]: species },
        })),
      resetSubmitForm: () =>
        set({
          filesByMode: {
            promoters_pre: { ...emptyFiles },
            promoters: { ...emptyFiles },
            intervals: { ...emptyFiles },
          },
          pathsByMode: {
            promoters_pre: { ...emptyPaths },
            promoters: { ...emptyPaths },
            intervals: { ...emptyPaths },
          },
          speciesByMode: { promoters_pre: '', promoters: '', intervals: '' },
        }),
    }),
    {
      // Only `mode` lives in localStorage. Files (with File objects),
      // paths, and species deliberately stay in-memory: persisting File
      // objects isn't possible across reload, and we don't want a stale
      // "you have foo.fasta uploaded" panel re-appearing in a fresh tab.
      // Surviving SPA navigation is enough — that's what the user lost.
      name: 'pmet-settings',
      partialize: (state) => ({ mode: state.mode }),
    },
  ),
);
