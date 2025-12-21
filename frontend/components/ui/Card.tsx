import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({ children, className = '', onClick }) => {
  const isClickable = !!onClick;
  const cardClasses = `
    bg-white rounded-xl shadow-md overflow-hidden border border-secondary-100
    ${isClickable ? 'cursor-pointer hover:shadow-2xl hover:-translate-y-1 hover:border-primary-200 transition-all duration-300 ease-out' : 'transition-shadow duration-200'}
    ${className}
  `;

  return (
    <div className={cardClasses} onClick={onClick}>
      {children}
    </div>
  );
};
