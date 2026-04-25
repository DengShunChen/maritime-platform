import React, { useState, useEffect, useRef, useCallback } from 'react';
import MapView from './components/MapView';
import TimeSlicer from './components/TimeSlicer';
import { KeyboardShortcutsHelp } from './components/KeyboardShortcutsHelp';

const App: React.FC = () => {
  const [currentTimeIndex, setCurrentTimeIndex] = useState<number>(0);
  const [timePoints, setTimePoints] = useState<number[]>([]);
  const [previewTimeIndex, setPreviewTimeIndex] = useState<number | null>(null);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const [dataFileKey, setDataFileKey] = useState(0);  // Triggers time points refresh

  // Animation state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const timerRef = useRef<number | null>(null);

  // Fetch time points (re-runs when dataFileKey changes)
  useEffect(() => {
    fetch('/api/time_points')
      .then(response => response.json())
      .then(data => {
        if (data.error) {
          console.error('Error in time points response:', data.error);
          return;
        }

        // Validate time points array
        if (!Array.isArray(data)) {
          console.error('Expected time points array, got:', typeof data);
          return;
        }

        // Handle empty array with fallback
        if (data.length === 0) {
          console.warn('⚠️ No time points from backend, using fallback time point at index 0');
          // Generate fallback: single time point at current time
          setTimePoints([Date.now()]);
          setCurrentTimeIndex(0);
          setIsPlaying(false);
          return;
        }

        // Valid data received
        const points = data.map((time: number) => time * 1000); // Convert to milliseconds
        console.log(`✅ Loaded ${points.length} time point(s) from backend`);
        setTimePoints(points);
        setCurrentTimeIndex(0); // Reset to first time point
        setIsPlaying(false);    // Stop playback on file change
      })
      .catch(error => {
        console.error('Error fetching time points:', error);
        // Fallback on fetch error
        console.warn('⚠️ Failed to fetch time points, using fallback');
        setTimePoints([Date.now()]);
        setCurrentTimeIndex(0);
        setIsPlaying(false);
      });
  }, [dataFileKey]);

  // Callback for MapView to trigger time points refresh
  const handleDataFileChange = useCallback(() => {
    setDataFileKey(prev => prev + 1);
  }, []);

  // Keyboard shortcuts handler
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Ignore if user is typing in an input
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      return;
    }

    switch (event.key) {
      case ' ': // Space - Play/Pause
        event.preventDefault();
        setIsPlaying(prev => !prev);
        break;
      case 'ArrowLeft': // Left arrow - Previous frame
        event.preventDefault();
        setCurrentTimeIndex(prev => Math.max(0, prev - 1));
        break;
      case 'ArrowRight': // Right arrow - Next frame
        event.preventDefault();
        setCurrentTimeIndex(prev => Math.min(timePoints.length - 1, prev + 1));
        break;
      case 'ArrowUp': // Up arrow - Speed up
        event.preventDefault();
        setPlaybackSpeed(prev => {
          const speeds = [0.5, 1, 2, 4];
          const idx = speeds.indexOf(prev);
          return speeds[Math.min(speeds.length - 1, idx + 1)] || prev;
        });
        break;
      case 'ArrowDown': // Down arrow - Slow down
        event.preventDefault();
        setPlaybackSpeed(prev => {
          const speeds = [0.5, 1, 2, 4];
          const idx = speeds.indexOf(prev);
          return speeds[Math.max(0, idx - 1)] || prev;
        });
        break;
      case 'Home': // Home - Go to first frame
        event.preventDefault();
        setCurrentTimeIndex(0);
        break;
      case 'End': // End - Go to last frame
        event.preventDefault();
        setCurrentTimeIndex(timePoints.length - 1);
        break;
      case 'f': // F - Toggle fullscreen
      case 'F':
        event.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen();
        }
        break;
      case '?': // ? - Show keyboard shortcuts help
        event.preventDefault();
        setShowShortcutsHelp(prev => !prev);
        break;
      case 'Escape': // Escape - Close help / exit fullscreen
        if (showShortcutsHelp) {
          setShowShortcutsHelp(false);
        }
        break;
    }
  }, [timePoints.length, showShortcutsHelp]);

  // Add keyboard event listener
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Animation Loop
  useEffect(() => {
    if (isPlaying && timePoints.length > 0) {
      if (timerRef.current) clearInterval(timerRef.current);

      const intervalMs = 1000 / playbackSpeed;

      timerRef.current = window.setInterval(() => {
        setCurrentTimeIndex(prevIndex => {
          const nextIndex = prevIndex + 1;
          if (nextIndex >= timePoints.length) {
            // Loop back to start
            return 0;
          }
          return nextIndex;
        });
      }, intervalMs);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, playbackSpeed, timePoints]);

  const handleTimeChange = (index: number) => {
    setCurrentTimeIndex(index);
    // Optional: Pause when manually dragging
    // setIsPlaying(false);
  };

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const handleSpeedChange = (speed: number) => {
    setPlaybackSpeed(speed);
  };

  // Use preview index if hovering, otherwise use current index
  const effectiveTimeIndex = previewTimeIndex !== null ? previewTimeIndex : currentTimeIndex;

  return (
    <div className="App">
      <MapView
        currentTimeIndex={effectiveTimeIndex}
        isPreview={previewTimeIndex !== null}
        onDataFileChange={handleDataFileChange}
      />
      <TimeSlicer
        timePoints={timePoints}
        onTimeChange={handleTimeChange}
        currentTimeIndex={currentTimeIndex}
        isPlaying={isPlaying}
        playbackSpeed={playbackSpeed}
        onTogglePlay={togglePlay}
        onSpeedChange={handleSpeedChange}
        onPreviewChange={setPreviewTimeIndex}
      />
      {showShortcutsHelp && (
        <KeyboardShortcutsHelp onClose={() => setShowShortcutsHelp(false)} />
      )}
    </div>
  );
};

export default App;