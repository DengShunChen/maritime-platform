import React, { useState, useRef, useEffect } from 'react';
import './SearchBar.css';

interface SearchResult {
  display_name: string;
  lat: string;
  lon: string;
}

interface SearchBarProps {
  onCoordinates: (lat: number, lon: number) => void;
}

export const SearchBar: React.FC<SearchBarProps> = ({ onCoordinates }) => {
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const parseCoordinates = (input: string) => {
    const cleaned = input.trim().replace(/\s+/g, '');
    const parts = cleaned.split(',');
    if (parts.length !== 2) return null;
    const first = Number(parts[0]);
    const second = Number(parts[1]);
    if (Number.isNaN(first) || Number.isNaN(second)) return null;

    const absFirst = Math.abs(first);
    const absSecond = Math.abs(second);

    if (absFirst <= 90 && absSecond <= 180) {
      return { lat: first, lon: second };
    }
    if (absFirst <= 180 && absSecond <= 90) {
      return { lat: second, lon: first };
    }
    return null;
  };

  const searchLocation = async (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setResults([]);
      setShowDropdown(false);
      return;
    }

    // First check if it's coordinates
    const coords = parseCoordinates(searchQuery);
    if (coords) {
      setResults([]);
      setShowDropdown(false);
      return;
    }

    setIsLoading(true);
    try {
      // Use OpenStreetMap Nominatim API for geocoding
      // Bias results toward East Asia region
      const url = new URL('https://nominatim.openstreetmap.org/search');
      url.searchParams.set('q', searchQuery);
      url.searchParams.set('format', 'json');
      url.searchParams.set('limit', '5');
      url.searchParams.set('viewbox', '100,50,150,10'); // East Asia bounding box
      url.searchParams.set('bounded', '0'); // Don't strictly limit to viewbox

      const response = await fetch(url.toString(), {
        headers: {
          'Accept-Language': 'zh-TW,zh,en',
          'User-Agent': 'MaritimePlatform/1.0'
        }
      });

      if (!response.ok) throw new Error('Geocoding failed');

      const data: SearchResult[] = await response.json();
      setResults(data);
      setShowDropdown(data.length > 0);
      setError(null);
    } catch (err) {
      console.error('Geocoding error:', err);
      setResults([]);
      setShowDropdown(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (value: string) => {
    setQuery(value);
    setError(null);

    // Debounce search
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      searchLocation(value);
    }, 300);
  };

  const handleSelectResult = (result: SearchResult) => {
    const lat = parseFloat(result.lat);
    const lon = parseFloat(result.lon);
    setQuery(result.display_name.split(',')[0]); // Show short name
    setShowDropdown(false);
    setResults([]);
    onCoordinates(lat, lon);
  };

  const handleSubmit = () => {
    // First try coordinates
    const coords = parseCoordinates(query);
    if (coords) {
      setError(null);
      setShowDropdown(false);
      onCoordinates(coords.lat, coords.lon);
      return;
    }

    // If there are search results, select the first one
    if (results.length > 0) {
      handleSelectResult(results[0]);
      return;
    }

    // Trigger search if no results yet
    searchLocation(query);
  };

  return (
    <div className="search-bar-container" ref={containerRef}>
      <div className="search-icon">
        {isLoading ? (
          <div className="search-spinner" />
        ) : (
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
        )}
      </div>
      <input
        type="text"
        placeholder="搜尋地點或輸入座標..."
        className="search-input"
        value={query}
        onChange={(event) => handleInputChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            handleSubmit();
          }
          if (event.key === 'Escape') {
            setShowDropdown(false);
          }
        }}
        onFocus={() => {
          if (results.length > 0) setShowDropdown(true);
        }}
      />
      <div className="menu-icon">
        <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="12" x2="21" y2="12"></line>
          <line x1="3" y1="6" x2="21" y2="6"></line>
          <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>
      </div>

      {/* Search Results Dropdown */}
      {showDropdown && results.length > 0 && (
        <div className="search-dropdown">
          {results.map((result, index) => (
            <button
              key={index}
              className="search-result-item"
              onClick={() => handleSelectResult(result)}
            >
              <span className="result-icon">📍</span>
              <span className="result-text">{result.display_name}</span>
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="search-error" role="status">
          {error}
        </div>
      )}
    </div>
  );
};
