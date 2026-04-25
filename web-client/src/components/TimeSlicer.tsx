import React, { useMemo, useState, useRef, useCallback } from 'react';
import './TimeSlicer.css';

interface TimeSlicerProps {
  timePoints: number[]; 
  currentTimeIndex: number; 
  isPlaying: boolean;
  playbackSpeed: number;
  onTimeChange: (index: number) => void;
  onTogglePlay: () => void;
  onSpeedChange: (speed: number) => void;
  onPreviewChange?: (index: number | null) => void; 
}

export const TimeSlicer: React.FC<TimeSlicerProps> = ({
  timePoints,
  currentTimeIndex,
  isPlaying,
  playbackSpeed,
  onTimeChange,
  onTogglePlay,
  onSpeedChange,
  onPreviewChange
}) => {
  const min = 0;
  const max = timePoints.length > 0 ? timePoints.length - 1 : 0;
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [hoverX, setHoverX] = useState<number>(0);
  const trackRef = useRef<HTMLDivElement>(null);

  const formatTime = useCallback((timestamp: number) => {
    const date = new Date(timestamp);
    const dStr = date.toLocaleDateString('zh-TW', { weekday: 'short', month: '2-digit', day: '2-digit' });
    const tStr = date.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', hour12: false });
    return { dateStr: dStr, timeStr: tStr, hour: date.getHours() };
  }, []);

  const { dateStr, timeStr } = useMemo(() => {
    if (!timePoints.length) return { dateStr: '--', timeStr: '--:--' };
    return formatTime(timePoints[currentTimeIndex]);
  }, [timePoints, currentTimeIndex, formatTime]);

  // Calculate day/night bands
  const dayNightBands = useMemo(() => {
    if (!timePoints.length) return [];
    return timePoints.map(t => {
      const hour = new Date(t).getHours();
      return (hour >= 6 && hour < 18) ? 'day' : 'night';
    });
  }, [timePoints]);

  const handleTrackMouseMove = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!trackRef.current || !timePoints.length) return;
    const rect = trackRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const percent = Math.max(0, Math.min(1, x / rect.width));
    const index = Math.round(percent * max);
    setHoverIndex(index);
    setHoverX(x);
    onPreviewChange?.(index);
  }, [max, timePoints.length, onPreviewChange]);

  const handleTrackMouseLeave = useCallback(() => {
    setHoverIndex(null);
    onPreviewChange?.(null);
  }, [onPreviewChange]);

  const progressPercent = max > 0 ? (currentTimeIndex / max) * 100 : 0;

  return (
    <div className="time-slicer-container glass-panel">
      {/* Precision Clock Display */}
      <div className="time-display-block">
        <div className="time-value">{timeStr}</div>
        <div className="date-value">{dateStr}</div>
        <div className="timezone-tag">UTC+8</div>
      </div>

      <div className="time-main-controls">
        <div className="playback-group">
          <button 
            className={`btn-play ${isPlaying ? 'is-playing' : ''}`} 
            onClick={onTogglePlay}
          >
            <div className="play-icon-container">
              {isPlaying ? (
                <div className="icon-pause" />
              ) : (
                <div className="icon-play" />
              )}
            </div>
          </button>
          
          <div className="speed-selector">
            {[1, 2, 4].map(s => (
              <button 
                key={s}
                className={`speed-tag ${playbackSpeed === s ? 'active' : ''}`}
                onClick={() => onSpeedChange(s)}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        <div 
          className="timeline-rail-wrapper" 
          ref={trackRef}
          onMouseMove={handleTrackMouseMove}
          onMouseLeave={handleTrackMouseLeave}
        >
          {/* Day/Night Band Background */}
          <div className="day-night-indicator">
            {dayNightBands.map((type, i) => (
              <div 
                key={i} 
                className={`dn-segment ${type}`} 
                style={{ width: `${100 / timePoints.length}%` }} 
              />
            ))}
          </div>

          <div className="timeline-rail-background" />
          <div className="timeline-rail-progress" style={{ width: `${progressPercent}%` }} />
          
          {/* Hover Tooltip */}
          {hoverIndex !== null && (
            <div className="timeline-hover-card" style={{ left: `${hoverX}px` }}>
              <span className="card-time">{formatTime(timePoints[hoverIndex]).timeStr}</span>
              <div className="card-arrow" />
            </div>
          )}

          <input
            type="range"
            min={min}
            max={max}
            value={currentTimeIndex}
            onChange={(e) => onTimeChange(parseInt(e.target.value))}
            className="timeline-slider"
          />
        </div>
      </div>
    </div>
  );
};

export default TimeSlicer;
