'use client';

import { Suspense, useState, useEffect, useCallback } from 'react';
import { taskApi } from '@/lib/api';
import { TaskResponse } from '@/lib/types';
import TaskCard from '@/components/TaskCard';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/lib/i18n';

// Search ?q= survives navigating away and back so results don't vanish on
// tab switch. A query that contains '@' is treated as an email (exact match);
// otherwise it's a task_id substring filter — both wired into the API.
function parseQuery(raw: string): { email?: string; task_id?: string } {
  const q = raw.trim();
  if (!q) return {};
  return q.includes('@') ? { email: q } : { task_id: q };
}

export default function TasksPage() {
  // useSearchParams forces this route off the static-prerender path; the
  // Suspense boundary below makes that explicit so `next build` is happy.
  return (
    <Suspense fallback={<div className="max-w-5xl mx-auto py-12 text-slate-500">Loading…</div>}>
      <TasksPageInner />
    </Suspense>
  );
}

const STORAGE_KEY = 'pmet:tasks:lastQuery';

function TasksPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();

  const urlQuery = searchParams.get('q') ?? '';
  const [searchInput, setSearchInput] = useState(urlQuery);
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [loading, setLoading] = useState(false);

  // If the URL has no ?q= but we remember a previous search this session,
  // restore it. This covers the case where the user clicks the navbar
  // "My Tasks" link (a plain href="/tasks" that drops the query) and
  // expects their last search to still be there.
  useEffect(() => {
    if (urlQuery) return;
    if (typeof window === 'undefined') return;
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      router.replace(`/tasks?q=${encodeURIComponent(saved)}`);
    }
  }, [urlQuery, router]);

  const fetchTasks = useCallback(async (q: string, showLoading = true) => {
    const filter = parseQuery(q);
    if (!filter.email && !filter.task_id) {
      setTasks([]);
      return;
    }
    if (showLoading) setLoading(true);
    try {
      const response = await taskApi.list(filter);
      setTasks(response.tasks);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  // Re-run search whenever the URL ?q= changes (covers navigation back to
  // the page) and keep the input box synced with whatever's in the URL.
  useEffect(() => {
    setSearchInput(urlQuery);
    fetchTasks(urlQuery);
  }, [urlQuery, fetchTasks]);

  // Poll while pending/running tasks are visible.
  useEffect(() => {
    if (!urlQuery) return;
    if (!tasks.some((task) => task.status === 'pending' || task.status === 'running')) {
      return;
    }
    const interval = setInterval(() => fetchTasks(urlQuery, false), 5000);
    return () => clearInterval(interval);
  }, [tasks, urlQuery, fetchTasks]);

  const handleSearch = () => {
    const q = searchInput.trim();
    if (!q) return;
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(STORAGE_KEY, q);
    }
    router.push(`/tasks?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">{t('tasks.title')}</h1>
        <button
          onClick={() => router.push('/submit')}
          className="btn-primary"
        >
          {t('tasks.new')}
        </button>
      </div>

      <div className="card mb-6">
        <label className="block text-sm text-slate-600 mb-2">
          {t('tasks.search.label')}
        </label>
        <div className="flex gap-4">
          <input
            type="text"
            className="input-field flex-1"
            placeholder={t('tasks.search.placeholder')}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button
            onClick={handleSearch}
            disabled={!searchInput.trim()}
            className="btn-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t('tasks.search.button')}
          </button>
        </div>
      </div>

      {!urlQuery ? (
        <div className="text-center py-12 text-slate-500">
          {t('tasks.empty.no_query')}
        </div>
      ) : loading ? (
        <div className="text-center py-12 text-slate-500">{t('tasks.empty.loading')}</div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12 text-slate-500">
          {t('tasks.empty.none_prefix')} <span className="font-mono">{urlQuery}</span>.
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map((task) => (
            <TaskCard
              key={task.task_id}
              task={task}
              onSelect={() => router.push(`/tasks/${task.task_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
