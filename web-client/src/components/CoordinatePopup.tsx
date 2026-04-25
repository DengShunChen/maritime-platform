import React, { useState, useEffect } from 'react';
import './CoordinatePopup.css';

interface CoordinatePopupProps {
  lat: number;
  lon: number;
  x: number;
  y: number;
  variable: string;
  timeIndex: number;
  onClose: () => void;
  onCopy: () => void;
}

interface ProbeResult {
  value: number | null;
  units: string;
  variable: string;
}

interface TimeSeriesData {
  values: (number | null)[];
}

export const CoordinatePopup: React.FC<CoordinatePopupProps> = ({
  lat,
  lon,
  x,
  y,
  variable,
  timeIndex,
  onClose,
  onCopy
}) => {
  const [probeData, setProbeData] = useState<ProbeResult | null>(null);
  const [seriesData, setSeriesData] = useState<TimeSeriesData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const probeVar = variable === 'WIND' ? 'WSPD' : variable;
    
    // Fetch both point data and time series
    Promise.all([
      fetch(`/api/probe?lat=${lat}&lon=${lon}&variable=${probeVar}&time=${timeIndex}`).then(res => res.json()),
      fetch(`/api/time_series?lat=${lat}&lon=${lon}&variable=${probeVar}`).then(res => res.json())
    ]).then(([probeRes, seriesRes]) => {
      if (!probeRes.error) setProbeData(probeRes);
      if (!seriesRes.error) setSeriesData(seriesRes);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [lat, lon, variable, timeIndex]);

  const renderSparkline = () => {
    if (!seriesData || !seriesData.values.length) return null;
    
    const vals = seriesData.values.filter((v): v is number => v !== null);
    if (vals.length < 2) return null;

    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    
    const width = 180;
    const height = 40;
    const points = seriesData.values.map((v, i) => {
      if (v === null) return null;
      const px = (i / (seriesData.values.length - 1)) * width;
      const py = height - ((v - min) / range) * height;
      return `${px},${py}`;
    });

    const pathData = points.filter(p => p !== null).join(' ');
    
    // Current point highlight
    const currentX = (timeIndex / (seriesData.values.length - 1)) * width;
    const currentY = seriesData.values[timeIndex] !== null 
      ? height - ((seriesData.values[timeIndex]! - min) / range) * height
      : 0;

    return (
      <div className="sparkline-container">
        <div className="sparkline-header">
          <span>趨勢 (全時段)</span>
          <span className="sparkline-range">{min.toFixed(1)} ~ {max.toFixed(1)}</span>
        </div>
        <svg width={width} height={height} className="sparkline-svg">
          <polyline
            fill="none"
            stroke="var(--windy-accent-alt)"
            strokeWidth="2"
            strokeLinejoin="round"
            points={pathData}
          />
          {seriesData.values[timeIndex] !== null && (
            <circle cx={currentX} cy={currentY} r="3" fill="#fff" />
          )}
        </svg>
      </div>
    );
  };

  const formatCoord = (value: number, isLat: boolean) => {
    const abs = Math.abs(value);
    const deg = Math.floor(abs);
    const min = Math.floor((abs - deg) * 60);
    const sec = ((abs - deg - min / 60) * 3600).toFixed(1);
    const dir = isLat ? (value >= 0 ? 'N' : 'S') : (value >= 0 ? 'E' : 'W');
    return `${deg}° ${min}' ${sec}" ${dir}`;
  };

  return (
    <div
      className="coordinate-popup glass-panel"
      style={{
        left: `${x}px`,
        top: `${y}px`
      }}
    >
      <div className="popup-content">
        <div className="popup-header">
          <span className="popup-title">📍 數據分析</span>
          <button className="popup-close-icon" onClick={onClose}>×</button>
        </div>

        <div className="popup-data-section">
          {loading ? (
            <div className="probe-loading">分析中...</div>
          ) : probeData ? (
            <>
              <div className="probe-result">
                <div className="probe-label">{probeData.variable}</div>
                <div className="probe-value-container">
                  <span className="probe-main-value">
                    {probeData.value !== null ? probeData.value : '--'}
                  </span>
                  <span className="probe-units">{probeData.units}</span>
                </div>
              </div>
              {renderSparkline()}
            </>
          ) : (
            <div className="probe-error">無法讀取數據</div>
          )}
        </div>

        <div className="popup-divider" />

        <div className="popup-coords">
          <div className="coord-row">
            <span className="coord-label">經緯度</span>
            <span className="coord-value">{lat.toFixed(4)}, {lon.toFixed(4)}</span>
          </div>
          <div className="coord-row dms">
            <span className="coord-dms">{formatCoord(lat, true)} | {formatCoord(lon, false)}</span>
          </div>
        </div>
        
        <div className="popup-actions">
          <button className="popup-btn copy" onClick={onCopy}>
            複製座標
          </button>
        </div>
      </div>
      <div className="popup-arrow" />
    </div>
  );
};
