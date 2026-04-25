import React, { useMemo } from 'react';
import './ColorLegend.css';

interface ColorLegendProps {
  variable: string;
  variableName: string;
  units: string;
  valueRange: [number, number];
  colormap?: string;
}

const COLORMAP_GRADIENTS: Record<string, string> = {
  'viridis': 'linear-gradient(to right, #440154, #3b528b, #21918c, #5ec962, #fde724)',
  'rdylbu_r': 'linear-gradient(to right, #313695, #4575b4, #abd9e9, #fee090, #fdae61, #f46d43, #d73027)',
  'ylgnbu': 'linear-gradient(to right, #ffffd9, #edf8b1, #c7e9b4, #7fcdbb, #41b6c4, #1d91c0, #225ea8)',
  'rdbu_r': 'linear-gradient(to right, #2166ac, #4393c3, #92c5de, #f7f7f7, #f4a582, #d6604d, #b2182b)',
  'gist_ncar': 'linear-gradient(to right, #000080, #0080ff, #00ffff, #00ff00, #ffff00, #ff8000, #ff0000)',
  'plasma': 'linear-gradient(to right, #0d0887, #7e03a8, #cc4778, #f89441, #f0f921)'
};

const VARIABLE_COLOR_SCHEMES: Record<string, string> = {
  'PSFC': 'viridis',
  'T2': 'rdylbu_r',
  'RAINC': 'ylgnbu',
  'RAINNC': 'ylgnbu',
  'U10': 'rdbu_r',
  'V10': 'rdbu_r',
  'REFD_MAX': 'gist_ncar',
  'WSPD': 'plasma'
};

export const ColorLegend: React.FC<ColorLegendProps> = ({
  variable,
  variableName,
  units,
  valueRange,
  colormap
}) => {
  const gradient = useMemo(() => {
    const scheme = (colormap?.toLowerCase() && COLORMAP_GRADIENTS[colormap.toLowerCase()])
      ? colormap.toLowerCase()
      : (VARIABLE_COLOR_SCHEMES[variable] || 'viridis');
    return COLORMAP_GRADIENTS[scheme] || COLORMAP_GRADIENTS['viridis'];
  }, [colormap, variable]);

  const [min, max] = valueRange;
  
  // Calculate 5 tick points
  const ticks = useMemo(() => {
    const step = (max - min) / 4;
    return [
      min,
      min + step,
      min + step * 2,
      min + step * 3,
      max
    ];
  }, [min, max]);

  return (
    <div className="color-legend glass-panel">
      <div className="legend-header">
        <span className="legend-title">{variableName}</span>
        <span className="legend-units">{units}</span>
      </div>
      
      <div className="legend-visual">
        <div className="legend-gradient-bar" style={{ background: gradient }} />
        <div className="legend-ticks">
          {ticks.map((_, i) => (
            <div key={i} className="legend-tick-mark" />
          ))}
        </div>
      </div>

      <div className="legend-labels">
        {ticks.map((val, i) => (
          <span key={i} className="legend-label">
            {val.toFixed(val > 100 ? 0 : 1)}
          </span>
        ))}
      </div>
    </div>
  );
};
