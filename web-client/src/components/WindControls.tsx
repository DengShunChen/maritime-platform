import React, { useState } from 'react';
import './WindControls.css';

// Available color schemes for wind particles
const COLOR_SCHEMES = [
  { id: 'viridis', name: '綠紫', gradient: 'linear-gradient(90deg, #440154, #3b528b, #21918c, #5ec962, #fde724)' },
  { id: 'turbo', name: '彩虹', gradient: 'linear-gradient(90deg, #30123b, #4145ab, #4f8cce, #aff467, #f9fb0e, #fb8b24, #d93807)' },
  { id: 'plasma', name: '暖色', gradient: 'linear-gradient(90deg, #0c0786, #6a00a8, #cb4778, #f79342, #f0f921)' },
  { id: 'cool', name: '冷色', gradient: 'linear-gradient(90deg, #00ffff, #00bfff, #0080ff, #0040ff, #8000ff)' },
  { id: 'magma', name: '岩漿', gradient: 'linear-gradient(90deg, #000003, #3b0f6f, #8c2980, #dd4968, #fdb42f, #fcfcba)' }
];

interface WindControlsProps {
  visible: boolean;
  fadeOpacity: number;
  speedFactor: number;
  particleSize: number;
  colorScheme?: string;
  onFadeOpacityChange: (value: number) => void;
  onSpeedFactorChange: (value: number) => void;
  onParticleSizeChange: (value: number) => void;
  onColorSchemeChange?: (colorScheme: string) => void;
}

export const WindControls: React.FC<WindControlsProps> = ({
  visible,
  fadeOpacity,
  speedFactor,
  particleSize,
  colorScheme = 'viridis',
  onFadeOpacityChange,
  onSpeedFactorChange,
  onParticleSizeChange,
  onColorSchemeChange
}) => {
  const [expanded, setExpanded] = useState(false);

  if (!visible) return null;

  return (
    <div className={`wind-controls ${expanded ? 'expanded' : ''}`}>
      <button
        className="wind-controls-toggle"
        onClick={() => setExpanded(!expanded)}
        aria-label={expanded ? '收合風場設定' : '展開風場設定'}
      >
        <span className="toggle-icon">🍃</span>
        <span className="toggle-label">風場設定</span>
        <span className={`toggle-arrow ${expanded ? 'up' : 'down'}`}>▼</span>
      </button>

      {expanded && (
        <div className="wind-controls-panel">
          {/* Trail Length (Fade Opacity) */}
          <div className="control-group">
            <label className="control-label">
              <span className="label-text">軌跡長度</span>
              <span className="label-value">{Math.round((1 - fadeOpacity) * 1000)}%</span>
            </label>
            <input
              type="range"
              className="control-slider"
              min="0.9"
              max="0.99"
              step="0.005"
              value={fadeOpacity}
              onChange={(e) => onFadeOpacityChange(parseFloat(e.target.value))}
            />
            <div className="slider-labels">
              <span>短</span>
              <span>長</span>
            </div>
          </div>

          {/* Animation Speed */}
          <div className="control-group">
            <label className="control-label">
              <span className="label-text">動畫速度</span>
              <span className="label-value">{speedFactor.toFixed(2)}x</span>
            </label>
            <input
              type="range"
              className="control-slider"
              min="0.1"
              max="1.0"
              step="0.05"
              value={speedFactor}
              onChange={(e) => onSpeedFactorChange(parseFloat(e.target.value))}
            />
            <div className="slider-labels">
              <span>慢</span>
              <span>快</span>
            </div>
          </div>

          {/* Particle Size */}
          <div className="control-group">
            <label className="control-label">
              <span className="label-text">粒子大小</span>
              <span className="label-value">{particleSize.toFixed(1)}px</span>
            </label>
            <input
              type="range"
              className="control-slider"
              min="1"
              max="8"
              step="0.5"
              value={particleSize}
              onChange={(e) => onParticleSizeChange(parseFloat(e.target.value))}
            />
            <div className="slider-labels">
              <span>小</span>
              <span>大</span>
            </div>
          </div>

          {/* Color Scheme Selector */}
          {onColorSchemeChange && (
            <div className="control-group">
              <label className="control-label">
                <span className="label-text">粒子色帶</span>
              </label>
              <div className="color-scheme-grid">
                {COLOR_SCHEMES.map(scheme => (
                  <button
                    key={scheme.id}
                    className={`color-scheme-button ${colorScheme === scheme.id ? 'active' : ''}`}
                    onClick={() => onColorSchemeChange(scheme.id)}
                    title={scheme.name}
                  >
                    <div
                      className="color-scheme-preview"
                      style={{ background: scheme.gradient }}
                    />
                    <span className="color-scheme-name">{scheme.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Presets */}
          <div className="control-presets">
            <button
              className="preset-button"
              onClick={() => {
                onFadeOpacityChange(0.97);
                onSpeedFactorChange(0.4);
                onParticleSizeChange(4.0);
              }}
            >
              預設
            </button>
            <button
              className="preset-button"
              onClick={() => {
                onFadeOpacityChange(0.99);
                onSpeedFactorChange(0.3);
                onParticleSizeChange(2.5);
              }}
            >
              細緻
            </button>
            <button
              className="preset-button"
              onClick={() => {
                onFadeOpacityChange(0.94);
                onSpeedFactorChange(0.6);
                onParticleSizeChange(5.0);
              }}
            >
              強勁
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
