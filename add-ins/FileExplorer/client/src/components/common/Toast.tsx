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

type ToastType = 'info' | 'success' | 'error';

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
    setToasts((current) => current.filter((toast) => toast.id !== id));
    setCopiedId((current) => (current === id ? null : current));
  }, []);

  const copyMessage = useCallback(async (event: MouseEvent, id: number, message: string) => {
    event.stopPropagation();
    const ok = await copyToClipboard(message);
    if (!ok) return;
    setCopiedId(id);
    if (copiedTimer.current) window.clearTimeout(copiedTimer.current);
    copiedTimer.current = window.setTimeout(() => {
      setCopiedId((current) => (current === id ? null : current));
    }, 1200);
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, type, message }]);
      window.setTimeout(() => dismiss(id), type === 'error' ? 6000 : 3000);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div id="fx-toast-container" className="fx-toasts">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            id={`fx-toast-${toast.id}`}
            className={`fx-toast fx-toast-${toast.type}`}
            onClick={() => dismiss(toast.id)}
            role="status"
          >
            <span id={`fx-toast-message-${toast.id}`} className="fx-toastMessage">
              {toast.message}
            </span>
            <button
              id={`fx-toast-copy-${toast.id}`}
              type="button"
              className="fx-toastCopy"
              title={copiedId === toast.id ? 'Copied' : 'Copy'}
              aria-label="Copy message"
              onClick={(event) => void copyMessage(event, toast.id, toast.message)}
            >
              {copiedId === toast.id ? <IconCheck size={13} /> : <IconCopy size={13} />}
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
    return { showToast: (message) => console.log('[toast]', message) };
  }
  return ctx;
}
