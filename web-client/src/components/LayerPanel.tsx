import React, { useState } from 'react';
import './LayerPanel.css';
import type { VariableInfo } from '../types/api';

interface LayerPanelProps {
  variables: VariableInfo[];
  selectedVariable: string;
  onVariableChange: (variableId: string) => void;
  showWind: boolean;
  onToggleWind: (show: boolean) => void;
  isWindAvailable?: boolean;
  showContours: boolean;
  onToggleContours: (show: boolean) => void;
  layerOpacity?: number;
  onOpacityChange?: (opacity: number) => void;
  selectedLevel: number;
  onLevelChange: (level: number) => void;
}

const VARIABLE_ICONS: Record<string, string> = {
  'PSFC': 'P',
  'T2': 'T',
  'RAINC': 'R',
  'RAINNC': 'R',
  'U10': 'U',
  'V10': 'V',
  'REFD_MAX': 'Z',
  'WSPD': 'W',
  'T_LEV': 'T',
  'P_HYD': 'P',
  'WSPD_LEV': 'W',
  'REFL_10CM':'Z',
  'SST': 'S',
  'WAVE_HS': 'Hs',
  'WAVE_TP': 'Tp',
  'WAVE_DIR': 'Dir',
  'CURRENT_SPD': 'Cur',
  'SSH': 'η',
};

const CATEGORY_LABELS = {
  weather: '氣象',
  marine: '海象'
} as const;

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
  onOpacityChange,
  selectedLevel,
  onLevelChange
}) => {
  const [showOpacitySlider, setShowOpacitySlider] = useState(false);
  const [activeCategory, setActiveCategory] = useState<'weather' | 'marine'>('weather');
  const currentVar = variables.find(v => v.id === selectedVariable);
  const numLevels = currentVar?.numLevels ?? 1;
  const categoryVariables = variables.filter((variable) => (variable.category ?? 'weather') === activeCategory);
  const availableInCategory = categoryVariables.filter((variable) => variable.available !== false).length;

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

      {/* Vertical Level Slider */}
      {numLevels > 1 && (
        <div className="level-selector-container">
          <div className="level-header">
            <span>垂直高度 (層級): {selectedLevel}</span>
          </div>
          <input
            type="range"
            className="level-slider"
            min="0"
            max={numLevels - 1}
            step="1"
            value={selectedLevel}
            onChange={(e) => onLevelChange(parseInt(e.target.value))}
          />
          <div className="level-ticks">
            <span>地面 (0)</span>
            <span>高空 ({numLevels - 1})</span>
          </div>
          <div className="panel-divider" style={{ marginTop: '12px', marginBottom: '4px' }} />
        </div>
      )}

      <div className="panel-divider" />

      <div className="category-tabs" role="tablist" aria-label="資料分類">
        {(['weather', 'marine'] as const).map((category) => (
          <button
            key={category}
            className={`category-tab ${activeCategory === category ? 'active' : ''}`}
            onClick={() => setActiveCategory(category)}
            role="tab"
            aria-selected={activeCategory === category}
          >
            {CATEGORY_LABELS[category]}
          </button>
        ))}
      </div>

      {/* Main Grid: Variable Selection */}
      <div className="variable-grid">
        {categoryVariables.map((variable) => {
          const isAvailable = variable.available !== false;
          return (
          <button
            key={variable.id}
            className={`variable-item ${selectedVariable === variable.id ? 'active' : ''} ${!isAvailable ? 'disabled' : ''}`}
            onClick={() => isAvailable && onVariableChange(variable.id)}
            disabled={!isAvailable}
          >
            <div className="item-icon">
              {VARIABLE_ICONS[variable.id] || variable.id.slice(0, 2)}
            </div>
            <div className="item-label">{variable.name}</div>
            {!isAvailable && <div className="item-unavailable">缺資料</div>}
            
            <span className="variable-tooltip">
              <strong>{variable.name}</strong>
              <p>{variable.description}</p>
              <div className="units">單位: {variable.units}</div>
            </span>
          </button>
        )})}
      </div>

      {availableInCategory === 0 && (
        <div className="category-empty">
          目前檔案尚未提供{CATEGORY_LABELS[activeCategory]}場。
        </div>
      )}
    </div>
  );
};
