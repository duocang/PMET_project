'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { adminApi, taskApi } from '@/lib/api';
import { TaskMode, TaskResponse, TaskStatus } from '@/lib/types';
import TaskCard from '@/components/TaskCard';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/lib/i18n';

// Search ?q= survives navigating away and back so results don't vanish on
// tab switch. A query that contains '@' is treated as an email (exact
// match); otherwise it's a task_id substring filter — both wired into the
// API. For admins the same input still drives the email/id filter, but the
// "no query → empty list" gate is dropped (admins always see everything).
function parseQuery(raw: string): { email?: string; task_id?: string } {
  const q = raw.trim();
  if (!q) return {};
  return q.includes('@') ? { email: q } : { task_id: q };
}

const STORAGE_KEY = 'pmet:tasks:lastQuery';

export default function TasksPage() {
  return (
    <Suspense fallback={<div className="max-w-5xl mx-auto py-12 text-slate-500">Loading…</div>}>
      <TasksPageInner />
    </Suspense>
  );
}

function TasksPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();

  const urlQuery = searchParams.get('q') ?? '';
  const [searchInput, setSearchInput] = useState(urlQuery);
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  // Admin-only filters
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [modeFilter, setModeFilter] = useState<TaskMode | 'all'>('all');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  // Detect admin once on mount.
  useEffect(() => {
    adminApi
      .me()
      .then((r) => setIsAdmin(r.is_admin))
      .catch(() => setIsAdmin(false));
  }, []);

  // Restore last search if URL has none (covers navbar tab clicks).
  useEffect(() => {
    if (urlQuery) return;
    if (typeof window === 'undefined') return;
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (saved) router.replace(`/tasks?q=${encodeURIComponent(saved)}`);
  }, [urlQuery, router]);

  const fetchTasks = useCallback(
    async (q: string, showLoading = true) => {
      const filter = parseQuery(q);
      // Non-admins must enter a query first — search is the access gate.
      // Admins see all tasks, even with no query, and rely on the filter
      // controls to narrow.
      if (!isAdmin && !filter.email && !filter.task_id) {
        setTasks([]);
        return;
      }
      if (showLoading) setLoading(true);
      try {
        const response = await taskApi.list(filter, 200);
        setTasks(response.tasks);
      } catch (error) {
        console.error('Failed to fetch tasks:', error);
      } finally {
        if (showLoading) setLoading(false);
      }
    },
    [isAdmin],
  );

  useEffect(() => {
    setSearchInput(urlQuery);
    if (isAdmin === null) return; // still detecting; avoid double-fetch
    fetchTasks(urlQuery);
  }, [urlQuery, fetchTasks, isAdmin]);

  // Poll while pending/running tasks are visible.
  useEffect(() => {
    if (isAdmin === null) return;
    if (!isAdmin && !urlQuery) return;
    if (!tasks.some((task) => task.status === 'pending' || task.status === 'running')) {
      return;
    }
    const interval = setInterval(() => fetchTasks(urlQuery, false), 5000);
    return () => clearInterval(interval);
  }, [tasks, urlQuery, fetchTasks, isAdmin]);

  const handleSearch = () => {
    const q = searchInput.trim();
    if (typeof window !== 'undefined') {
      if (q) window.sessionStorage.setItem(STORAGE_KEY, q);
      else window.sessionStorage.removeItem(STORAGE_KEY);
    }
    router.push(q ? `/tasks?q=${encodeURIComponent(q)}` : '/tasks');
  };

  // Client-side filter pass for the admin-only knobs (status / mode / date).
  // We do these client-side so the backend stays simple; with limit=200 the
  // payload is tiny and the user never sees more than a screenful at a time.
  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      if (statusFilter !== 'all' && task.status !== statusFilter) return false;
      if (modeFilter !== 'all' && task.mode !== modeFilter) return false;
      const created = new Date(task.created_at).getTime();
      if (dateFrom) {
        const from = new Date(dateFrom).getTime();
        if (Number.isFinite(from) && created < from) return false;
      }
      if (dateTo) {
        // dateTo input is YYYY-MM-DD — extend to end of day so the upper
        // bound is inclusive of any task created on that date.
        const to = new Date(dateTo + 'T23:59:59').getTime();
        if (Number.isFinite(to) && created > to) return false;
      }
      return true;
    });
  }, [tasks, statusFilter, modeFilter, dateFrom, dateTo]);

  const handleCancel = async (taskId: string) => {
    const reason = window.prompt(t('admin.cancel.prompt')) ?? undefined;
    // null = user cancelled the dialog → don't proceed; '' = pressed OK with
    // empty input → use default email body.
    if (reason === undefined && reason !== null) return;
    if (reason === null) return;
    try {
      await taskApi.cancel(taskId, reason);
      fetchTasks(urlQuery, false);
    } catch (e: any) {
      alert(e?.response?.data?.detail || t('admin.cancel.error'));
    }
  };

  const showEmpty =
    !isAdmin && !urlQuery; // non-admin with no query → please-search prompt

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">
          {isAdmin ? t('tasks.title.admin') : t('tasks.title')}
        </h1>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <button
              onClick={() => router.push('/admin/settings')}
              className="text-sm text-slate-500 hover:text-slate-700"
            >
              {t('tasks.admin.settings_link')}
            </button>
          )}
          <button onClick={() => router.push('/submit')} className="btn-primary">
            {t('tasks.new')}
          </button>
        </div>
      </div>

      <div className="card mb-6 space-y-4">
        <div>
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
              className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={!isAdmin && !searchInput.trim()}
            >
              {t('tasks.search.button')}
            </button>
          </div>
          {/* Stale-input hint: results below correspond to ?q=, but the
              user has edited the box without re-submitting. Surface that
              gap so the list isn't silently misaligned with the search
              text. Cheap visual cue, no new behavior. */}
          {searchInput.trim() !== urlQuery && (
            <p className="mt-1 text-xs text-amber-700">
              {t('tasks.search.stale_hint')}
            </p>
          )}
        </div>

        {isAdmin && (
          <div className="grid gap-3 border-t border-slate-200 pt-4 md:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
                {t('tasks.filter.status')}
              </label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
                className="input-field"
              >
                <option value="all">{t('tasks.filter.all')}</option>
                <option value="pending">{t('tasks.status.pending')}</option>
                <option value="running">{t('tasks.status.running')}</option>
                <option value="completed">{t('tasks.status.completed')}</option>
                <option value="failed">{t('tasks.status.failed')}</option>
                <option value="cancelled">{t('tasks.status.cancelled')}</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
                {t('tasks.filter.mode')}
              </label>
              <select
                value={modeFilter}
                onChange={(e) => setModeFilter(e.target.value as TaskMode | 'all')}
                className="input-field"
              >
                <option value="all">{t('tasks.filter.all')}</option>
                <option value="promoters_pre">{t('mode.promoters_pre')}</option>
                <option value="promoters">{t('mode.promoters')}</option>
                <option value="intervals">{t('mode.intervals')}</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
                {t('tasks.filter.from')}
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="input-field"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
                {t('tasks.filter.to')}
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="input-field"
              />
            </div>
          </div>
        )}
      </div>

      {/* What query the list below actually represents. Search is
          submit-only, so we surface the "active query" explicitly to
          stop the input box and the rendered list from silently
          drifting apart in the user's mental model. */}
      {urlQuery && !showEmpty && (
        <p className="mb-3 text-xs text-slate-500">
          {t('tasks.results_for')} <span className="font-mono text-slate-700">{urlQuery}</span>
        </p>
      )}

      {showEmpty ? (
        <div className="text-center py-12 text-slate-500">{t('tasks.empty.no_query')}</div>
      ) : loading ? (
        <div className="text-center py-12 text-slate-500">{t('tasks.empty.loading')}</div>
      ) : filteredTasks.length === 0 ? (
        <div className="text-center py-12 text-slate-500">
          {urlQuery ? (
            <>
              {t('tasks.empty.none_prefix')} <span className="font-mono">{urlQuery}</span>.
            </>
          ) : (
            t('tasks.empty.admin_no_match')
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {filteredTasks.map((task) => (
            <div key={task.task_id} className="relative">
              <TaskCard task={task} onSelect={() => router.push(`/tasks/${task.task_id}`)} />
              {isAdmin && (task.status === 'pending' || task.status === 'running') && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCancel(task.task_id);
                  }}
                  className="absolute right-4 top-4 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                >
                  {t('admin.cancel.button')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
