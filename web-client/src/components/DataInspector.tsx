import React from 'react';
import './DataInspector.css';

interface DataInspectorProps {
  lat: number | null;
  lon: number | null;
  value: number | null;
  direction?: number | null;
  units: string;
  variableName: string;
}

export const DataInspector: React.FC<DataInspectorProps> = ({
  lat,
  lon,
  value,
  direction,
  units,
  variableName
}) => {
  if (lat === null || lon === null) return null;

  const getCompassDirection = (deg: number) => {
    const directions = ['北', '東北', '東', '東南', '南', '西南', '西', '西北'];
    return directions[Math.round(deg / 45) % 8];
  };

  const isWind = variableName.includes('風');

  return (
    <div className="data-inspector glass-panel">
      <div className="inspector-item">
        <span className="ins-label">位置</span>
        <span className="ins-value">{lat.toFixed(3)}°N, {lon.toFixed(3)}°E</span>
      </div>
      <div className="inspector-divider" />
      <div className="inspector-item main">
        <span className="ins-label">{variableName}</span>
        <div className="ins-value-group">
          <span className="ins-value">
            {value !== null ? `${value.toFixed(1)} ${units}` : '--'}
          </span>
          {isWind && direction !== undefined && direction !== null && (
            <div className="wind-info">
              <span className="wind-direction-text">{getCompassDirection(direction)}風</span>
              <div 
                className="wind-arrow" 
                style={{ transform: `rotate(${direction}deg)` }}
                title={`${direction}°`}
              >
                ↑
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
