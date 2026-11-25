import { useCallback, useEffect, useState } from 'react';

import { onEvent, sendJsLog } from '../connector/fusionBridge';
import type { Theme } from '../types/types';
import { SelectByList } from './SelectByList';
import { ToastProvider } from './common/Toast';

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(systemTheme);

  const applyTheme = useCallback((next: Theme | null | undefined) => {
    setTheme(next ?? systemTheme());
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    return onEvent('themeChanged', (raw) => {
      try {
        const data = JSON.parse(raw) as { theme?: Theme | null };
        applyTheme(data.theme);
      } catch {
        // Ignore malformed pushes.
      }
    });
  }, [applyTheme]);

  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      sendJsLog('error', event.message || 'window.error', {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
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

  return (
    <ToastProvider>
      <SelectByList onTheme={applyTheme} />
    </ToastProvider>
  );
}
