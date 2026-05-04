'use client';

import { useCallback, useState } from 'react';
import { useDropzone, type FileError, type FileRejection } from 'react-dropzone';
import toast from 'react-hot-toast';
import { useTranslation } from '@/lib/i18n';
import { formatBytes } from '@/lib/runtime';
import FilePreview from './FilePreview';

export interface ExampleItem {
  /** Display label, already humanised + extension-stripped. */
  label: string;
  /** URL to fetch the file blob from. */
  url: string;
  /** Filename to give the fetched file when handed to runUpload. */
  filename: string;
}

// Same palette as GeneClusterFilter / scripts/r/process_pmet_result.R so
// chip colours stay stable across the submit form, the gene-cluster
// filter, and downstream visualisations. Index modulo length covers any
// future catalog growth past 7 entries.
const EXAMPLE_PALETTE = [
  '#ed3333', // red
  '#1a94bc', // blue
  '#40a070', // green
  '#fc6315', // orange
  '#f9a633', // mustard
  '#8b2671', // purple
  '#2f2f35', // near-black
];

interface FileUploadProps {
  label: string;
  accept?: string;
  /**
   * Caller does the actual upload. The optional onProgress callback is
   * forwarded all the way down to axios's onUploadProgress so the box
   * fill reflects real bytes-on-wire instead of a fake animation.
   */
  onUpload: (file: File, onProgress?: (pct: number) => void) => Promise<void>;
  /** Caller deletes the previously-uploaded file (server + local state). */
  onClear?: () => Promise<void> | void;
  currentFile?: string;
  /** Size in bytes of the currently-uploaded file. When set, the
   *  uploaded-state panel renders "<filename> (123 MB)" so users get the
   *  same size hint here as on download buttons. */
  currentFileSize?: number;
  helpText?: string;
  required?: boolean;
  /** Optional URL to a demo file. If set, a small "Use example" link appears. */
  demoUrl?: string;
  /** Filename to give the fetched demo file. */
  demoFilename?: string;
  /** Multi-example chip row. When provided, replaces the single
   *  "Use example" button with a row of coloured chips — click any chip
   *  to load that file into the upload slot. Useful when a slot has
   *  several equally-valid example sources (e.g. multiple motif DBs). */
  examples?: ExampleItem[];
  /** Optional inline format preview. Renders a "查看示例" trigger next to
   *  "使用示例"; clicking opens a side drawer showing `previewContent`.
   *  All three props must be set together; if any is missing, no preview
   *  trigger appears. */
  previewTitle?: string;
  previewContent?: string;
  previewNote?: string;
}

function UploadIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-slate-400"
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function FileCheckIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-emerald-500"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <polyline points="9 14 11 16 15 12" />
    </svg>
  );
}

export default function FileUpload({
  label,
  accept,
  onUpload,
  onClear,
  currentFile,
  currentFileSize,
  helpText,
  required = false,
  demoUrl,
  demoFilename,
  examples,
  previewTitle,
  previewContent,
  previewNote,
}: FileUploadProps) {
  const { t } = useTranslation();
  const [loadingDemo, setLoadingDemo] = useState(false);
  // Tracks which chip in the multi-example row is mid-fetch so we can
  // show a per-chip spinner without disabling the rest more than
  // necessary. null = nothing in flight.
  const [loadingExampleUrl, setLoadingExampleUrl] = useState<string | null>(null);
  // Multi-example picker visibility. Stays false until the user clicks
  // "Use example" so the dropzone keeps the same height as its grid
  // siblings until they actually want to pick. Auto-resets when an
  // upload starts or completes (currentFile / uploading take over the
  // visual region).
  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadingFilename, setUploadingFilename] = useState<string>('');
  const [removing, setRemoving] = useState(false);

  const acceptedExtensions = accept
    ? accept
        .split(',')
        .map((ext) => ext.trim().toLowerCase())
        .filter(Boolean)
    : [];

  const runUpload = useCallback(
    async (file: File) => {
      // Tiny files (and the "use example" path) finish in <100 ms; the
      // green progress bar would flash by before the user sees there
      // was even an upload. Pad the visible "uploading" state to a
      // 1.5 s floor so the animation always plays through. Real long
      // uploads exceed this naturally and aren't affected.
      const MIN_VISIBLE_MS = 1500;
      const start = Date.now();
      setUploading(true);
      setProgress(0);
      setUploadingFilename(file.name);
      try {
        await onUpload(file, setProgress);
        const elapsed = Date.now() - start;
        if (elapsed < MIN_VISIBLE_MS) {
          await new Promise((r) => setTimeout(r, MIN_VISIBLE_MS - elapsed));
        }
        toast.success(`${file.name} — ${t('fileupload.toast.uploaded')}`);
      } catch (error) {
        toast.error(`${t('fileupload.toast.failed')}: ${file.name}`);
        console.error(error);
      } finally {
        setUploading(false);
        setProgress(0);
        setUploadingFilename('');
      }
    },
    [onUpload, t]
  );

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      await runUpload(acceptedFiles[0]);
    },
    [runUpload]
  );

  const validateFileType = useCallback(
    (file: File): FileError | null => {
      if (acceptedExtensions.length === 0) return null;
      const fileName = file.name.toLowerCase();
      const isAccepted = acceptedExtensions.some((ext) => fileName.endsWith(ext));
      if (isAccepted) return null;
      return {
        code: 'file-invalid-type',
        message: `File type must be ${acceptedExtensions.join(', ')}`,
      };
    },
    [acceptedExtensions]
  );

  const onDropRejected = useCallback(
    (fileRejections: FileRejection[]) => {
      const firstError = fileRejections[0]?.errors[0];
      toast.error(firstError?.message || t('fileupload.toast.unsupported'));
    },
    [t]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    multiple: false,
    disabled: uploading || !!currentFile,
    validator: acceptedExtensions.length > 0 ? validateFileType : undefined,
  });

  const fetchAndUpload = useCallback(
    async (url: string, filename: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const file = new File([blob], filename, { type: blob.type || 'application/octet-stream' });
      await runUpload(file);
    },
    [runUpload]
  );

  const useExample = useCallback(async () => {
    if (!demoUrl) return;
    setLoadingDemo(true);
    try {
      const filename = demoFilename || demoUrl.split('/').pop() || 'example';
      await fetchAndUpload(demoUrl, filename);
      toast.success(`${t('fileupload.toast.example_loaded')} ${filename}`);
    } catch (e) {
      toast.error(t('fileupload.toast.example_failed'));
      console.error(e);
    } finally {
      setLoadingDemo(false);
    }
  }, [demoUrl, demoFilename, fetchAndUpload, t]);

  const useExampleChip = useCallback(
    async (item: ExampleItem) => {
      setLoadingExampleUrl(item.url);
      try {
        await fetchAndUpload(item.url, item.filename);
        toast.success(`${t('fileupload.toast.example_loaded')} ${item.filename}`);
        setPickerOpen(false);
      } catch (e) {
        toast.error(t('fileupload.toast.example_failed'));
        console.error(e);
      } finally {
        setLoadingExampleUrl(null);
      }
    },
    [fetchAndUpload, t]
  );

  const handleRemove = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!onClear) return;
      setRemoving(true);
      try {
        await onClear();
        toast.success(t('fileupload.removed'));
      } catch (err) {
        toast.error(t('fileupload.remove_failed'));
        console.error(err);
      } finally {
        setRemoving(false);
      }
    },
    [onClear, t]
  );

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1">
        <label className="label mb-0">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
        <div className="flex items-center gap-3">
          {previewTitle && previewContent && (
            <FilePreview
              title={previewTitle}
              content={previewContent}
              note={previewNote}
              triggerLabel={t('fileupload.preview_example')}
              closeLabel={t('viz.modal.close')}
            />
          )}
          {/* Single-demoUrl flow: clicking immediately fetches + uploads.
              Multi-example flow: clicking toggles the in-box chip picker
              (default hidden so the box height stays aligned with the
              siblings). */}
          {(demoUrl || (examples && examples.length > 0)) && !currentFile && !uploading && (
            <button
              type="button"
              onClick={
                examples && examples.length > 0
                  ? () => setPickerOpen((v) => !v)
                  : useExample
              }
              disabled={loadingDemo || loadingExampleUrl !== null}
              className="text-xs font-medium text-primary-700 hover:text-primary-800 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="13 2 13 9 20 9" />
                <path d="M20 9v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h7" />
              </svg>
              {loadingDemo
                ? t('fileupload.loading')
                : examples && pickerOpen
                  ? t('fileupload.hide_examples')
                  : t('fileupload.use_example')}
            </button>
          )}
        </div>
      </div>
      <div
        {...getRootProps()}
        className={`file-upload ${isDragActive ? 'border-primary-500 bg-primary-50' : ''} ${uploading || currentFile ? 'cursor-default' : ''}`}
      >
        <input {...getInputProps({ accept })} />

        {uploading && (
          <div
            className="file-upload-charge"
            style={{ width: `${progress}%` }}
            aria-hidden="true"
          />
        )}

        <div className="relative space-y-3">
          {uploading ? (
            <>
              <div className="flex justify-center"><UploadIcon /></div>
              <p className="text-sm font-medium text-emerald-700">
                {t('fileupload.uploading')} <span className="font-mono break-all">{uploadingFilename}</span>
              </p>
              {acceptedExtensions.length > 0 && (
                <p className="text-xs invisible" aria-hidden="true">
                  {t('fileupload.drop_idle_hint')} <span className="font-mono">{acceptedExtensions.join(' · ')}</span>
                </p>
              )}
            </>
          ) : currentFile ? (
            <>
              <div className="flex justify-center"><FileCheckIcon /></div>
              <p className="font-medium text-emerald-700 break-all">
                {currentFile}
                {currentFileSize != null && (
                  <span className="ml-1 font-normal text-emerald-600/80">
                    ({formatBytes(currentFileSize)})
                  </span>
                )}
              </p>
              {onClear && (
                <button
                  type="button"
                  onClick={handleRemove}
                  disabled={removing}
                  className="inline-flex items-center gap-1 text-xs font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6" />
                    <path d="M14 11v6" />
                    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                  </svg>
                  {removing ? t('fileupload.loading') : t('fileupload.remove')}
                </button>
              )}
            </>
          ) : isDragActive ? (
            <>
              <div className="flex justify-center"><UploadIcon /></div>
              <p className="text-primary-600">{t('fileupload.drop_active')}</p>
            </>
          ) : pickerOpen && examples && examples.length > 0 ? (
            // In-box chip picker: same vertical footprint as the idle
            // prompt, so the box height matches sibling upload slots in
            // the grid. stopPropagation on each chip prevents the
            // dropzone's click-to-open-file-dialog from firing.
            <>
              <p className="text-xs text-slate-500">{t('fileupload.examples_label')}</p>
              <div
                className="flex flex-wrap items-center justify-center gap-1.5"
                onClick={(e) => e.stopPropagation()}
              >
                {examples.map((item, i) => {
                  const color = EXAMPLE_PALETTE[i % EXAMPLE_PALETTE.length];
                  const isLoading = loadingExampleUrl === item.url;
                  const anyLoading = loadingExampleUrl !== null;
                  return (
                    <button
                      key={item.url}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        useExampleChip(item);
                      }}
                      disabled={anyLoading}
                      title={item.filename}
                      className="rounded-full border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                      style={{ backgroundColor: `${color}33` }}
                    >
                      {isLoading ? `${item.label}…` : item.label}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <div className="flex justify-center"><UploadIcon /></div>
              <p className="text-slate-600">{t('fileupload.drop_idle')}</p>
              {acceptedExtensions.length > 0 && (
                <p className="text-xs text-slate-400">
                  {t('fileupload.drop_idle_hint')} <span className="font-mono">{acceptedExtensions.join(' · ')}</span>
                </p>
              )}
            </>
          )}
        </div>
      </div>
      {helpText && (
        <p className="mt-1 text-sm text-slate-500">{helpText}</p>
      )}
    </div>
  );
}
