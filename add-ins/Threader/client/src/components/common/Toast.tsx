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

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, type, message }]);
      window.setTimeout(() => dismiss(id), type === 'error' ? 6000 : 3000);
    },
    [dismiss]
  );

  const copyMessage = useCallback(async (event: MouseEvent, id: number, message: string) => {
    event.stopPropagation();
    const ok = await copyToClipboard(message);
    if (ok) setCopiedId(id);
  }, []);

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div id="th_toastContainer" className="th_toastContainer">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            id={`th_toast_${toast.id}`}
            className={`th_toast th_toast_${toast.type}`}
            onClick={() => dismiss(toast.id)}
            role="status"
          >
            <span id={`th_toastMessage_${toast.id}`} className="th_toastMessage">
              {toast.message}
            </span>
            <button
              id={`th_toastCopy_${toast.id}`}
              type="button"
              className="th_toastCopy"
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
  if (!ctx) return { showToast: (message) => console.log('[toast]', message) };
  return ctx;
}
