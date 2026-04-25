import React from 'react';
import './LoadingOverlay.css';

interface LoadingOverlayProps {
  isLoading: boolean;
  message?: string;
  progress?: number; // 0-100
}

export const LoadingOverlay: React.FC<LoadingOverlayProps> = ({
  isLoading,
  message = '載入中...',
  progress
}) => {
  if (!isLoading) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-content">
        <div className="loading-spinner">
          <svg viewBox="0 0 50 50">
            <circle
              cx="25"
              cy="25"
              r="20"
              fill="none"
              strokeWidth="4"
              className="spinner-track"
            />
            <circle
              cx="25"
              cy="25"
              r="20"
              fill="none"
              strokeWidth="4"
              className="spinner-fill"
              strokeDasharray="125.6"
              strokeDashoffset="100"
            />
          </svg>
        </div>
        <div className="loading-message">{message}</div>
        {progress !== undefined && (
          <div className="loading-progress-container">
            <div 
              className="loading-progress-bar"
              style={{ width: `${progress}%` }}
            />
            <span className="loading-progress-text">{Math.round(progress)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};
