import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { Toast, ToastProps } from '../components/ui/Toast.tsx';

type ToastOptions = Omit<ToastProps, 'onDismiss' | 'id'>;

interface ToastContextType {
  addToast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

export const ToastProvider = ({ children }: { children: ReactNode }) => {
  const [toasts, setToasts] = useState<ToastProps[]>([]);

  const addToast = useCallback((options: ToastOptions) => {
    const id = Date.now();
    const onDismiss = () => {
      setToasts(currentToasts => currentToasts.filter(t => t.id !== id));
    };
    setToasts(currentToasts => [...currentToasts, { ...options, id, onDismiss }]);
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-3">
        {toasts.map(toast => (
          <Toast key={toast.id} {...toast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};
