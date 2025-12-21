
import React, { useState, useEffect } from 'react';
import { X, AlertCircle, CheckCircle } from 'lucide-react';

export interface ToastProps {
  id: number;
  message: string;
  type?: 'success' | 'error' | 'info';
  duration?: number;
  onDismiss: () => void;
}

const typeStyles = {
  success: {
    icon: <CheckCircle className="text-green-500" />,
    bar: 'bg-green-500',
  },
  error: {
    icon: <AlertCircle className="text-red-500" />,
    bar: 'bg-red-500',
  },
  info: {
    icon: <AlertCircle className="text-blue-500" />,
    bar: 'bg-blue-500',
  },
};

export const Toast: React.FC<ToastProps> = ({
  message,
  type = 'info',
  duration = 5000,
  onDismiss,
}) => {
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsExiting(true);
      setTimeout(onDismiss, 500); // Match animation duration
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onDismiss]);

  const handleDismiss = () => {
    setIsExiting(true);
    setTimeout(onDismiss, 500);
  };

  const { icon, bar } = typeStyles[type];
  const animationClass = isExiting ? 'animate-toast-out' : 'animate-toast-in';

  return (
    <div
      className={`flex items-center bg-white shadow-lg rounded-lg overflow-hidden w-80 ${animationClass}`}
      role="alert"
    >
      <div className={`w-1.5 h-full ${bar}`}></div>
      <div className="flex items-center p-4">
        <div className="flex-shrink-0">{icon}</div>
        <div className="ml-3 text-sm font-medium text-secondary-700">
          {message}
        </div>
      </div>
      <button onClick={handleDismiss} className="ml-auto p-4 text-secondary-400 hover:text-secondary-600">
        <X size={18} />
      </button>
    </div>
  );
};

export const ToastContainer = () => {
  // This is a placeholder. The actual toasts are rendered by ToastProvider.
  return <div id="toast-container" className="fixed bottom-5 right-5 z-50 flex flex-col gap-3"></div>;
};
