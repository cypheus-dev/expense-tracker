import React from 'react';
import { Card } from '@/components/ui/card';

// Wspólny nagłówek sekcji używany w wielu miejscach
export const SectionHeader = ({ title, action }) => (
  <div className="flex justify-between items-center p-4 bg-white border-b">
    <h5 className="text-lg font-medium text-gray-900 m-0">{title}</h5>
    {action && (
      <div className="flex gap-2">
        {action}
      </div>
    )}
  </div>
);

// Ujednolicony komponent karty z możliwością dodania akcji w nagłówku
export const ContentCard = ({ title, action, children, className = '' }) => (
  <Card className={`bg-white shadow-sm ${className}`}>
    <SectionHeader title={title} action={action} />
    <div className="p-4">
      {children}
    </div>
  </Card>
);

// Komponent statystyki używany w raportach
export const StatCard = ({ title, value, subtitle, color = 'primary' }) => {
  const colors = {
    primary: 'text-blue-600',
    info: 'text-cyan-600',
    success: 'text-green-600',
    warning: 'text-yellow-600'
  };

  return (
    <Card className="bg-white shadow-sm">
      <div className="p-4">
        <h5 className="text-sm font-medium text-gray-600 mb-2">{title}</h5>
        <h2 className={`text-2xl font-bold ${colors[color]} mb-1`}>{value}</h2>
        <p className="text-sm text-gray-500 m-0">{subtitle}</p>
      </div>
    </Card>
  );
};

// Komponent przycisku z ikoną używany w wielu miejscach
export const IconButton = ({ icon, label, variant = 'primary', onClick, size = 'md' }) => {
  const baseClasses = 'inline-flex items-center justify-center gap-2 font-medium rounded-lg';
  const variants = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200',
    danger: 'bg-red-600 text-white hover:bg-red-700'
  };
  const sizes = {
    sm: 'px-2.5 py-1.5 text-sm',
    md: 'px-4 py-2',
    lg: 'px-6 py-3 text-lg'
  };

  return (
    <button 
      className={`${baseClasses} ${variants[variant]} ${sizes[size]}`}
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
};

// Komponent tabeli z nagłówkiem używany w listach wydatków i konfiguracji
export const DataTable = ({ headers, children, className = '' }) => (
  <div className={`overflow-x-auto ${className}`}>
    <table className="w-full min-w-full divide-y divide-gray-200">
      <thead className="bg-gray-50">
        <tr>
          {headers.map((header, index) => (
            <th 
              key={index}
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-200">
        {children}
      </tbody>
    </table>
  </div>
);

export default {
  SectionHeader,
  ContentCard,
  StatCard,
  IconButton,
  DataTable
};