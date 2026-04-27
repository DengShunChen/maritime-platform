import React, { useState } from 'react';
import './LayerPanel.css';

interface Variable {
  id: string;
  name: string;
  description: string;
  units: string;
}

interface LayerPanelProps {
  variables: Variable[];
  selectedVariable: string;
  onVariableChange: (variableId: string) => void;
  showWind: boolean;
  onToggleWind: (show: boolean) => void;
  isWindAvailable?: boolean;
  showContours: boolean;
  onToggleContours: (show: boolean) => void;
  layerOpacity?: number;
  onOpacityChange?: (opacity: number) => void;
}

const VARIABLE_ICONS: Record<string, string> = {
  'PSFC': '🌡️',      // Surface Pressure
  'T2': '🌡️',        // Temperature
  'RAINC': '🌧️',     // Cumulus Precipitation
  'RAINNC': '☔',    // Grid Scale Precipitation
  'U10': '💨',       // U-Wind
  'V10': '🌬️',       // V-Wind
  'REFD_MAX': '⚡',   // Radar Reflectivity
};

export const LayerPanel: React.FC<LayerPanelProps> = ({
  variables,
  selectedVariable,
  onVariableChange,
  showWind,
  onToggleWind,
  isWindAvailable = true,
  showContours,
  onToggleContours,
  layerOpacity = 0.2,
  onOpacityChange
}) => {
  const [showOpacitySlider, setShowOpacitySlider] = useState(false);

  return (
    <div className="layer-panel glass-panel">
      {/* Top Section: Controls */}
      <div className="panel-controls">
        {isWindAvailable && (
          <button
            className={`control-btn wind-toggle ${showWind ? 'active' : ''}`}
            onClick={() => onToggleWind(!showWind)}
            title="切換風場流動動畫"
          >
            <span className="icon">🍃</span>
            <span className="label">風場</span>
          </button>
        )}

        <button
          className={`control-btn contour-toggle ${showContours ? 'active' : ''}`}
          onClick={() => onToggleContours(!showContours)}
          title="切換等壓/等值線"
        >
          <span className="icon">〰️</span>
          <span className="label">等值線</span>
        </button>

        <button
          className={`control-btn opacity-btn ${showOpacitySlider ? 'active' : ''}`}
          onClick={() => setShowOpacitySlider(!showOpacitySlider)}
          title="調整底圖不透明度"
        >
          <span className="icon">◐</span>
        </button>
      </div>

      {showOpacitySlider && onOpacityChange && (
        <div className="panel-popover opacity-popover">
          <div className="popover-header">底圖不透明度: {Math.round(layerOpacity * 100)}%</div>
          <input
            type="range"
            className="opacity-slider"
            min="0.1"
            max="1"
            step="0.05"
            value={layerOpacity}
            onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
          />
        </div>
      )}

      <div className="panel-divider" />

      {/* Main Grid: Variable Selection */}
      <div className="variable-grid">
        {variables.map((variable) => (
          <button
            key={variable.id}
            className={`variable-item ${selectedVariable === variable.id ? 'active' : ''}`}
            onClick={() => onVariableChange(variable.id)}
          >
            <div className="item-icon">
              {VARIABLE_ICONS[variable.id] || '📊'}
            </div>
            <div className="item-label">{variable.name}</div>
            
            <span className="variable-tooltip">
              <strong>{variable.name}</strong>
              <p>{variable.description}</p>
              <div className="units">單位: {variable.units}</div>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};
