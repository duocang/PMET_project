import { create } from 'zustand';

interface AdminStore {
  isAdmin: boolean;
  checked: boolean;
  setStatus: (isAdmin: boolean) => void;
  reset: () => void;
}

export const useAdminStore = create<AdminStore>((set) => ({
  isAdmin: false,
  checked: false,
  setStatus: (isAdmin) => set({ isAdmin, checked: true }),
  reset: () => set({ isAdmin: false, checked: false }),
}));
