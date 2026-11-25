import { IconX } from '@tabler/icons-react';
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

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
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = nextId.current++;
      setToasts((current) => [...current.slice(-2), { id, type, message }]);
      window.setTimeout(() => dismiss(id), type === 'error' ? 6000 : 3000);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div id="sbl-toast-container" className="sbl-toasts">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            id={`sbl-toast-${toast.id}`}
            className={`sbl-toast sbl-toast-${toast.type}`}
            onClick={() => dismiss(toast.id)}
            role="status"
          >
            <span id={`sbl-toast-message-${toast.id}`} className="sbl-toastMessage">
              {toast.message}
            </span>
            <IconX id={`sbl-toast-close-${toast.id}`} size={13} className="sbl-toastClose" />
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
