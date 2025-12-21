
import React from 'react';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', className = '' }) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  return (
    <div
      className={`animate-spin rounded-full border-t-2 border-b-2 border-primary-600 ${sizeClasses[size]} ${className}`}
      role="status"
      aria-live="polite"
    >
        <span className="sr-only">Loading...</span>
    </div>
  );
};
