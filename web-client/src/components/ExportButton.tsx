import React, { useState } from 'react';
import maplibregl from 'maplibre-gl';
import './ExportButton.css';

interface ExportButtonProps {
  mapRef: React.RefObject<maplibregl.Map | null>;
  getWindCanvas?: () => HTMLCanvasElement | null;
}

export const ExportButton: React.FC<ExportButtonProps> = ({ mapRef, getWindCanvas }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  const exportMap = async (format: 'png' | 'jpg', includeWind: boolean = true) => {
    if (!mapRef.current) return;

    setIsExporting(true);
    setShowMenu(false);

    try {
      const map = mapRef.current;
      const mapCanvas = map.getCanvas();

      // Create a temporary canvas to composite layers
      const exportCanvas = document.createElement('canvas');
      exportCanvas.width = mapCanvas.width;
      exportCanvas.height = mapCanvas.height;
      const ctx = exportCanvas.getContext('2d');

      if (!ctx) {
        throw new Error('Could not get canvas context');
      }

      // Draw the map canvas
      ctx.drawImage(mapCanvas, 0, 0);

      // Draw wind layer if available and requested
      const windCanvas = getWindCanvas?.();
      if (includeWind && windCanvas) {
        ctx.drawImage(windCanvas, 0, 0);
      }

      // Convert to blob and download
      const mimeType = format === 'png' ? 'image/png' : 'image/jpeg';
      const quality = format === 'jpg' ? 0.92 : undefined;

      exportCanvas.toBlob(
        (blob) => {
          if (!blob) {
            console.error('Failed to create blob');
            return;
          }

          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.download = `maritime-map-${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.${format}`;
          link.href = url;
          link.click();
          URL.revokeObjectURL(url);
        },
        mimeType,
        quality
      );
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="export-button-container">
      <button
        className={`export-button ${isExporting ? 'exporting' : ''}`}
        onClick={() => setShowMenu(!showMenu)}
        disabled={isExporting}
        aria-label="導出地圖"
      >
        {isExporting ? (
          <span className="export-spinner" />
        ) : (
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        )}
      </button>

      {showMenu && (
        <div className="export-menu">
          <button
            className="export-menu-item"
            onClick={() => exportMap('png', true)}
          >
            <span className="menu-icon">🖼️</span>
            <span className="menu-text">PNG（含風場）</span>
          </button>
          <button
            className="export-menu-item"
            onClick={() => exportMap('png', false)}
          >
            <span className="menu-icon">🗺️</span>
            <span className="menu-text">PNG（僅地圖）</span>
          </button>
          <button
            className="export-menu-item"
            onClick={() => exportMap('jpg', true)}
          >
            <span className="menu-icon">📷</span>
            <span className="menu-text">JPG（高畫質）</span>
          </button>
        </div>
      )}
    </div>
  );
};
