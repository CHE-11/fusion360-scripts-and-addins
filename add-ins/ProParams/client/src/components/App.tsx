import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

import { sendJsLog, sendReady } from '../connector/fusionBridge';
import type { TabId } from '../types/types';
import { GlobalTab } from './GlobalTab/GlobalTab';
import { ProjectTab } from './ProjectTab/ProjectTab';
import { SettingsDialog } from './SettingsDialog/SettingsDialog';
import { Tabs } from './Tabs/Tabs';
import { ToastProvider } from './common/Toast';

const DEFAULT_APP_WIDTH = 915;
const MIN_APP_WIDTH = 320;
const WIDTH_STORAGE_KEY = 'pp_app_width';

function viewportWidth(): number {
  return document.documentElement.clientWidth || window.innerWidth;
}

function fitAppWidth(preferred: number): number {
  const viewport = viewportWidth();
  const min = Math.min(MIN_APP_WIDTH, viewport);
  return Math.round(Math.min(Math.max(preferred, min), viewport));
}

function readPreferredWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    if (Number.isFinite(saved) && saved > 0) return saved;
  } catch {
    // Fusion's palette webview can block storage.
  }
  return DEFAULT_APP_WIDTH;
}

function persistWidth(width: number) {
  try {
    localStorage.setItem(WIDTH_STORAGE_KEY, String(width));
  } catch {
    // Ignore storage failures; the in-session width still applies.
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('project');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const preferredWidth = useRef(readPreferredWidth());
  const resizingRef = useRef(false);
  const [width, setWidth] = useState(() => fitAppWidth(preferredWidth.current));
  const [resizing, setResizing] = useState(false);

  useEffect(() => {
    // Handshake with the Fusion add-in so it can push data to us.
    void sendReady();

    const onError = (ev: ErrorEvent) => {
      sendJsLog('error', ev.message || 'window.error', {
        filename: ev.filename,
        lineno: ev.lineno,
        colno: ev.colno,
        stack: ev.error?.stack,
      });
    };
    const onRejection = (ev: PromiseRejectionEvent) => {
      const reason = ev.reason;
      sendJsLog('error', 'Unhandled promise rejection', {
        reason: String(reason),
        stack: reason instanceof Error ? reason.stack : undefined,
      });
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  useEffect(() => {
    const onResize = () => setWidth(fitAppWidth(preferredWidth.current));
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      document.body.classList.remove('pp_resizing');
    };
  }, []);

  const applyWidth = (preferred: number, persist: boolean) => {
    const next = fitAppWidth(preferred);
    preferredWidth.current = next;
    setWidth(next);
    if (persist) persistWidth(next);
  };

  const onResizePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    resizingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizing(true);
    document.body.classList.add('pp_resizing');
  };

  const onResizePointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (!resizingRef.current) return;
    const rootLeft = document.getElementById('root')?.getBoundingClientRect().left ?? 0;
    applyWidth(event.clientX - rootLeft, false);
  };

  const onResizePointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    if (!resizingRef.current) return;
    resizingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    document.body.classList.remove('pp_resizing');
    setResizing(false);
    persistWidth(preferredWidth.current);
  };

  const onResizeKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step = event.shiftKey ? 64 : 16;
    let next = preferredWidth.current;
    if (event.key === 'ArrowLeft') next -= step;
    else if (event.key === 'ArrowRight') next += step;
    else if (event.key === 'Home') next = DEFAULT_APP_WIDTH;
    else return;
    event.preventDefault();
    applyWidth(next, true);
  };

  return (
    <div
      id="pp_app"
      className={resizing ? 'pp_app pp_appResizing' : 'pp_app'}
      style={{ width }}
    >
      <ToastProvider>
        <Tabs active={activeTab} onChange={setActiveTab} openSettings={() => setSettingsOpen(true)} />

        <main id="pp_main" className="pp_main">
          {activeTab === 'global' && <GlobalTab />}
          {activeTab === 'project' && <ProjectTab />}
        </main>
        {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      </ToastProvider>
      <button
        id="pp_app_resize"
        className="pp_app_resize"
        type="button"
        aria-label="Resize panel"
        aria-valuemin={Math.min(MIN_APP_WIDTH, viewportWidth())}
        aria-valuemax={viewportWidth()}
        aria-valuenow={width}
        onPointerDown={onResizePointerDown}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        onPointerCancel={onResizePointerUp}
        onKeyDown={onResizeKeyDown}
      />
    </div>
  );
}
