import { IconCheck, IconCopy } from '@tabler/icons-react';
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react';

import { copyToClipboard } from '../../utils/clipboard';

type ToastType = 'info' | 'success' | 'error' | 'warning';

type Toast = {
  id: number;
  type: ToastType;
  message: string;
};

type ToastContextValue = {
  showToast: (message: string, type?: ToastType) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const nextId = useRef(1);
  const copiedTimer = useRef<number | null>(null);

  const dismiss = useCallback((id: number) => {
    setToasts((cur) => cur.filter((t) => t.id !== id));
    setCopiedId((cur) => (cur === id ? null : cur));
  }, []);

  const copyMessage = useCallback(async (event: MouseEvent, id: number, message: string) => {
    event.stopPropagation();
    const ok = await copyToClipboard(message);
    if (!ok) return;
    setCopiedId(id);
    if (copiedTimer.current) window.clearTimeout(copiedTimer.current);
    copiedTimer.current = window.setTimeout(() => {
      setCopiedId((cur) => (cur === id ? null : cur));
    }, 1200);
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = nextId.current++;
      setToasts((cur) => [...cur, { id, type, message }]);
      window.setTimeout(() => dismiss(id), type === 'error' || type === 'warning' ? 6000 : 3000);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div id="pp_toastContainer" className="pp_toastContainer">
        {toasts.map((t) => (
          <div
            key={t.id}
            id={`pp_toast_${t.id}`}
            className={`pp_toast pp_toast_${t.type}`}
            onClick={(event) => {
              if (event.target instanceof Element && event.target.closest('.pp_toastCopy')) return;
              dismiss(t.id);
            }}
            role="status"
          >
            <span id={`pp_toastMessage_${t.id}`} className="pp_toastMessage">
              {t.message}
            </span>
            <button
              id={`pp_toastCopy_${t.id}`}
              type="button"
              className="pp_toastCopy"
              title={copiedId === t.id ? 'Copied' : 'Copy'}
              aria-label="Copy message"
              onPointerDown={(event) => {
                // A focused copy button blurs the parameter editor and that blur saves the row.
                event.preventDefault();
                event.stopPropagation();
              }}
              onMouseDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              onClick={(event) => void copyMessage(event, t.id, t.message)}
            >
              {copiedId === t.id ? <IconCheck size={13} /> : <IconCopy size={13} />}
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Safe fallback so the hook never crashes outside a provider.
    return { showToast: (m) => console.log('[toast]', m) };
  }
  return ctx;
}
