import { useEffect, useState } from 'react';

import { IconFolder } from '@tabler/icons-react';

import { onEvent, request } from '../../connector/fusionBridge';
import type { BrowseParamsFileResult, ExportFormat, ExportProgress, ExportVariationsResult } from '../../types/types';
import { useToast } from '../common/Toast';

type Props = {
  fileCount: number;
  onClose: () => void;
};

const FORMATS: { id: ExportFormat; label: string }[] = [
  { id: 'step', label: 'STEP (.step)' },
  { id: 'stl', label: 'STL (.stl)' },
  { id: '3mf', label: '3MF (.3mf)' },
];

function fileName(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

export function ExportVariationsDialog({ fileCount, onClose }: Props) {
  const { showToast } = useToast();
  const [format, setFormat] = useState<ExportFormat>('step');
  const [folder, setFolder] = useState('');
  const [browsing, setBrowsing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState<ExportProgress | null>(null);
  const [result, setResult] = useState<ExportVariationsResult | null>(null);
  const [error, setError] = useState('');

  const busy = browsing || exporting;

  useEffect(() => {
    let cancelled = false;
    void request<{ path: string }>('project:defaultExportFolder')
      .then((result) => {
        if (!cancelled && result?.path) setFolder((current) => current || result.path);
      })
      .catch(() => {
        /* The folder field stays empty so the user can type or browse. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  useEffect(() => onEvent('exportProgress', (raw) => {
    try {
      setProgress(JSON.parse(raw) as ExportProgress);
    } catch {
      /* ignore malformed progress */
    }
  }), []);

  const browse = async () => {
    setBrowsing(true);
    setError('');
    try {
      const picked = await request<BrowseParamsFileResult>('project:browseExportFolder', {
        folder: folder.trim(),
      });
      if (!picked.cancelled && picked.path) setFolder(picked.path);
    } catch (browseError) {
      setError(String(browseError));
    } finally {
      setBrowsing(false);
    }
  };

  const runExport = async () => {
    setExporting(true);
    setError('');
    setResult(null);
    setProgress(null);
    try {
      const exported = await request<ExportVariationsResult>('project:exportVariations', {
        format,
        folder: folder.trim(),
      });
      setResult(exported);
      const failed = exported.errors.length;
      if (failed === 0) {
        showToast(
          `Exported ${exported.exported} file${exported.exported === 1 ? '' : 's'}.`,
          'success'
        );
      } else if (exported.exported === 0) {
        showToast(exported.errors[0] ?? 'Export failed.', 'error');
      } else {
        showToast(
          `Exported ${exported.exported} of ${exported.exported + failed}. ${failed} failed.`,
          'warning'
        );
      }
    } catch (exportError) {
      const message = String(exportError);
      setError(message);
      showToast(message, 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div
      id="pp_exportBackdrop"
      className="pp_modalBackdrop"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <form
        id="pp_exportDialog"
        className="pp_modal"
        role="dialog"
        aria-labelledby="pp_exportTitle"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy && folder.trim() && !result) void runExport();
        }}
      >
        <header id="pp_exportHeader" className="pp_modalHeader">
          <h2 id="pp_exportTitle" className="pp_modalTitle">
            Export variations
          </h2>
        </header>

        <div id="pp_exportBody" className="pp_modalBody">
          <p id="pp_exportHelp" className="pp_help">
            {fileCount === 1
              ? 'Writes 1 file. Parameters without a variation list keep their current value. The design is restored when the export finishes.'
              : `Writes ${fileCount} files, one for each combination. Parameters without a variation list keep their current value. The design is restored when the export finishes.`}
          </p>

          <label id="pp_exportFormatLabel" className="pp_fieldLabel" htmlFor="pp_exportFormat">
            Format
          </label>
          <select
            id="pp_exportFormat"
            className="pp_input pp_select"
            value={format}
            disabled={busy || !!result}
            onChange={(event) => setFormat(event.target.value as ExportFormat)}
          >
            {FORMATS.map((item) => (
              <option id={`pp_exportFormat_${item.id}`} key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>

          <label id="pp_exportFolderLabel" className="pp_fieldLabel" htmlFor="pp_exportFolder">
            Folder
          </label>
          <div id="pp_exportFolderRow" className="pp_pathRow">
            <input
              id="pp_exportFolder"
              className="pp_input"
              type="text"
              value={folder}
              spellCheck={false}
              autoComplete="off"
              disabled={busy || !!result}
              placeholder="Downloads"
              onChange={(event) => setFolder(event.target.value)}
            />
            <button
              id="pp_exportBrowse"
              className="pp_btn"
              type="button"
              title="Choose a folder"
              disabled={busy || !!result}
              onClick={() => void browse()}
            >
              <IconFolder size={14} />
              Browse
            </button>
          </div>

          {exporting && (
            <p id="pp_exportProgress" className="pp_help">
              {progress
                ? `Exporting ${progress.index} of ${progress.total}: ${progress.label}`
                : 'Starting export…'}
            </p>
          )}

          {result && (
            <div id="pp_exportResult" className="pp_exportResult">
              <p id="pp_exportResultSummary" className="pp_help">
                Exported {result.exported} file{result.exported === 1 ? '' : 's'}.
              </p>
              {result.files.length > 0 && (
                <ul id="pp_exportFiles" className="pp_exportFiles">
                  {result.files.map((file, index) => (
                    <li id={`pp_exportFile_${index}`} key={file} title={file}>
                      {fileName(file)}
                    </li>
                  ))}
                </ul>
              )}
              {result.errors.length > 0 && (
                <ul id="pp_exportErrors" className="pp_exportErrors">
                  {result.errors.map((message, index) => (
                    <li id={`pp_exportError_${index}`} key={`${index}-${message}`}>
                      {message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {error && (
            <p id="pp_exportError" className="pp_formError">
              {error}
            </p>
          )}
        </div>

        <footer id="pp_exportFooter" className="pp_modalFooter">
          <button id="pp_exportCancel" className="pp_btn" type="button" disabled={exporting} onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </button>
          {!result && (
            <button
              id="pp_exportRun"
              className="pp_btn pp_btnPrimary"
              type="submit"
              disabled={busy || !folder.trim() || fileCount === 0}
            >
              {exporting ? 'Exporting…' : `Export ${fileCount}`}
            </button>
          )}
        </footer>
      </form>
    </div>
  );
}
