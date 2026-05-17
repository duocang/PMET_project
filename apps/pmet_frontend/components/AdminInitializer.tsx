'use client';

import { useEffect } from 'react';
import { adminApi } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';

export function AdminInitializer() {
  const setStatus = useAdminStore((s) => s.setStatus);
  useEffect(() => {
    adminApi
      .me()
      .then((r) => setStatus(r.is_admin))
      .catch(() => setStatus(false));
  }, [setStatus]);
  return null;
}
