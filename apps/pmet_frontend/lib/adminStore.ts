import { create } from 'zustand';

interface AdminStore {
  isAdmin: boolean;
  checked: boolean;
  // Mirrors the server-side `submissions_paused` admin setting.
  // Piggybacked on /admin/me so every visitor (not just admins) learns
  // about maintenance windows without an extra round-trip.
  submissionsPaused: boolean;
  setStatus: (isAdmin: boolean, submissionsPaused: boolean) => void;
  setSubmissionsPaused: (paused: boolean) => void;
  reset: () => void;
}

export const useAdminStore = create<AdminStore>((set) => ({
  isAdmin: false,
  checked: false,
  submissionsPaused: false,
  setStatus: (isAdmin, submissionsPaused) =>
    set({ isAdmin, submissionsPaused, checked: true }),
  setSubmissionsPaused: (submissionsPaused) => set({ submissionsPaused }),
  reset: () => set({ isAdmin: false, checked: false, submissionsPaused: false }),
}));
