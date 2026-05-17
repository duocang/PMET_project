'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminApi } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';
import { useTranslation } from '@/lib/i18n';

interface Props {
  taskId: string;
  // Current note, if any — taken from the parent task data so we don't
  // re-fetch just to seed the editor.
  initialNote?: string | null;
}

export function AdminTaskPanel({ taskId, initialNote }: Props) {
  const { t } = useTranslation();
  const router = useRouter();
  const isAdmin = useAdminStore((s) => s.isAdmin);
  const checked = useAdminStore((s) => s.checked);

  const [debug, setDebug] = useState<{ meta: Record<string, unknown>; stderr_tail: string[] | null } | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [note, setNote] = useState(initialNote ?? '');
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteSavedAt, setNoteSavedAt] = useState<number | null>(null);
  const [rerunBusy, setRerunBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setNote(initialNote ?? '');
  }, [initialNote]);

  const loadDebug = async () => {
    setDebugLoading(true);
    setErr(null);
    try {
      const r = await adminApi.taskDebug(taskId);
      setDebug({ meta: r.meta, stderr_tail: r.stderr_tail });
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    } finally {
      setDebugLoading(false);
    }
  };

  const saveNote = async () => {
    setNoteSaving(true);
    setErr(null);
    try {
      await adminApi.taskSetNote(taskId, note.trim() || null);
      setNoteSavedAt(Date.now());
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    } finally {
      setNoteSaving(false);
    }
  };

  const rerun = async () => {
    if (!confirm(t('admin.task.rerun.confirm'))) return;
    setRerunBusy(true);
    setErr(null);
    try {
      const r = await adminApi.taskRerun(taskId);
      router.push(`/tasks/${r.task_id}`);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? e?.message ?? 'Failed');
    } finally {
      setRerunBusy(false);
    }
  };

  if (!checked || !isAdmin) return null;

  return (
    <div className="card border-amber-200 bg-amber-50/30 space-y-5">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-800">
        {t('admin.task.title')}
      </h2>

      {err && <div className="text-sm text-red-700">{err}</div>}

      {/* Admin note — visible as a banner to the user */}
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          {t('admin.task.note.label')}
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder={t('admin.task.note.placeholder')}
          className="input-field font-mono text-xs"
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={saveNote}
            disabled={noteSaving}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {noteSaving ? t('admin.task.note.saving') : t('admin.task.note.save')}
          </button>
          {noteSavedAt && (
            <span className="text-xs text-emerald-700">{t('admin.task.note.saved')}</span>
          )}
        </div>
        <p className="mt-1 text-xs text-slate-500">{t('admin.task.note.help')}</p>
      </div>

      {/* Rerun */}
      <div>
        <button
          onClick={rerun}
          disabled={rerunBusy}
          className="rounded-md border border-amber-400 bg-white px-3 py-1.5 text-sm font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50"
        >
          {rerunBusy ? t('admin.task.rerun.busy') : t('admin.task.rerun.button')}
        </button>
        <p className="mt-1 text-xs text-slate-500">{t('admin.task.rerun.help')}</p>
      </div>

      {/* Debug */}
      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            {t('admin.task.debug.title')}
          </h3>
          <button
            onClick={loadDebug}
            disabled={debugLoading}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {debugLoading ? t('admin.task.debug.loading') : (debug ? t('admin.task.debug.refresh') : t('admin.task.debug.load'))}
          </button>
        </div>
        {debug && (
          <div className="mt-2 space-y-2">
            <div>
              <div className="text-xs font-medium text-slate-600">{t('admin.task.debug.meta')}</div>
              <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-slate-100 px-3 py-2 font-mono text-xs text-slate-800">
                {JSON.stringify(debug.meta, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-xs font-medium text-slate-600">{t('admin.task.debug.stderr')}</div>
              {debug.stderr_tail && debug.stderr_tail.length > 0 ? (
                <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-slate-900 px-3 py-2 font-mono text-xs text-emerald-300">
                  {debug.stderr_tail.join('\n')}
                </pre>
              ) : (
                <div className="mt-1 text-xs text-slate-500">{t('admin.task.debug.stderr_empty')}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
