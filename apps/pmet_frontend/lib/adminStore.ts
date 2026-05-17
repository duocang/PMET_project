import { create } from 'zustand';

interface AdminStore {
  isAdmin: boolean;
  checked: boolean;
  // Mirrors the server-side `submissions_paused` admin setting.
  // Piggybacked on /admin/me so every visitor (not just admins) learns
  // about maintenance windows without an extra round-trip.
  submissionsPaused: boolean;
  // Bumped on every successful PUT /admin/settings. Sibling admin
  // panels subscribe to this so they re-fetch their derived views
  // (e.g. CleanupCard's "eligible" count when retention_days changes)
  // without needing a page reload or a polling interval.
  settingsVersion: number;
  setStatus: (isAdmin: boolean, submissionsPaused: boolean) => void;
  setSubmissionsPaused: (paused: boolean) => void;
  bumpSettings: () => void;
  reset: () => void;
}

export const useAdminStore = create<AdminStore>((set) => ({
  isAdmin: false,
  checked: false,
  submissionsPaused: false,
  settingsVersion: 0,
  setStatus: (isAdmin, submissionsPaused) =>
    set({ isAdmin, submissionsPaused, checked: true }),
  setSubmissionsPaused: (submissionsPaused) => set({ submissionsPaused }),
  bumpSettings: () => set((s) => ({ settingsVersion: s.settingsVersion + 1 })),
  reset: () => set({ isAdmin: false, checked: false, submissionsPaused: false }),
}));
