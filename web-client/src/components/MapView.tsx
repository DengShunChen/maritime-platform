import React, { useRef, useEffect, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import { WindLayer } from './WindLayer';
import { LayerPanel } from './LayerPanel';
import { ColorLegend } from './ColorLegend';
import { SearchBar } from './SearchBar';
import { WindControls } from './WindControls';
import { ExportButton } from './ExportButton';
import { CoordinatePopup } from './CoordinatePopup';
import { LoadingOverlay } from './LoadingOverlay';
import { useToast } from './Toast';
import { DataFileSelector } from './DataFileSelector';
import { DataInspector } from './DataInspector';
import { ForecastStatus } from './ForecastStatus';
import { LRUCache } from '../utils/LRUCache';
import { usePrefetch } from '../utils/dataPreloader';
import type { EtlStatus, VariableInfo, VariableStats } from '../types/api';
import type { Feature, FeatureCollection, LineString } from 'geojson';

interface MapViewProps {
  currentTimeIndex: number;
  timePointCount?: number;
  isPreview?: boolean;
  onDataFileChange?: () => void;
}

const MapView: React.FC<MapViewProps> = ({ currentTimeIndex, timePointCount = 0, isPreview = false, onDataFileChange }) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [lng] = useState(121.0);
  const [lat] = useState(24.0);
  const [zoom] = useState(3);
  const [mapLoaded, setMapLoaded] = useState(false);

  const [variables, setVariables] = useState<VariableInfo[]>([]);
  const [selectedVariable, setSelectedVariable] = useState('T2');
  const [selectedLevel, setSelectedLevel] = useState(0);
  const [showWind, setShowWind] = useState(true);
  const [isWindAvailable, setIsWindAvailable] = useState(false);
  const [showContours, setShowContours] = useState(true);

  const handleVariableChange = (varId: string) => {
    setSelectedVariable(varId);
    setSelectedLevel(0);
  };

  const [hoverData, setHoverData] = useState<{ value: number, direction?: number, units: string, variable: string } | null>(null);
  const [hoverPos, setHoverPos] = useState<{ lat: number, lon: number } | null>(null);
  const [isDataLoading, setIsDataLoading] = useState(false);
  const [dataRefreshKey, setDataRefreshKey] = useState(0);
  const { showToast } = useToast();

  const [valueRange, setValueRange] = useState<[number, number]>([0, 100]);
  const [legendColormap, setLegendColormap] = useState<string>('rdylbu_r');
  const [windLayer, setWindLayer] = useState<WindLayer | null>(null);

  const statsCacheRef = useRef(new LRUCache<string, VariableStats>(50));
  const cogManifestRef = useRef<Record<string, string[]>>({});
  const fallbackToastShownRef = useRef(false);

  const [windFadeOpacity, setWindFadeOpacity] = useState(0.985);
  const [windSpeedFactor, setWindSpeedFactor] = useState(0.9);
  const [windParticleSize, setWindParticleSize] = useState(2.0);
  const [windColorScheme, setWindColorScheme] = useState('windy');
  const [layerOpacity, setLayerOpacity] = useState(0.68);

  const [clickedCoord, setClickedCoord] = useState<{ lat: number; lon: number; x: number; y: number; } | null>(null);

  const removeLayerAndSource = (layerId: string, sourceId: string) => {
    if (!map.current) return;
    if (map.current.getLayer(layerId)) map.current.removeLayer(layerId);
    if (map.current.getSource(sourceId)) map.current.removeSource(sourceId);
  };

  usePrefetch(currentTimeIndex, timePointCount, selectedVariable, mapLoaded && !isPreview && timePointCount > 0);

  const ensureWindOnTop = useCallback(() => {
    // Canvas wind overlay sits above the MapLibre canvas by z-index.
  }, []);

  useEffect(() => {
    if (map.current) return;
    map.current = new maplibregl.Map({
      container: mapContainer.current!,
      style: `https://api.maptiler.com/maps/darkmatter/style.json?key=${import.meta.env.VITE_MAPTILER_API_KEY}`,
      center: [lng, lat],
      zoom: zoom
    });

    map.current.on('load', () => {
      if (!map.current) return;
      map.current.addControl(new maplibregl.NavigationControl(), 'top-right');
      map.current.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

      const lines: Feature<LineString>[] = [];
      for (let ln = -180; ln <= 180; ln += 10) {
        lines.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[ln, -85], [ln, 85]] } });
      }
      for (let lt = -80; lt <= 80; lt += 10) {
        lines.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[-180, lt], [180, lt]] } });
      }

      map.current.addSource('graticule-source', { type: 'geojson', data: { type: 'FeatureCollection', features: lines } });
      map.current.addLayer({ id: 'graticule-layer', type: 'line', source: 'graticule-source', paint: { 'line-color': 'rgba(255,255,255,0.1)', 'line-width': 1, 'line-dasharray': [2, 2] } });

      const wind = new WindLayer(map.current);
      wind.setParams({ fadeOpacity: 0.985, speedFactor: 0.9, particleSize: 2.0 });
      setWindLayer(wind);
      setMapLoaded(true);
    });

    map.current.on('error', (e) => {
      if (e && e.error && e.error.message) {
        console.warn('MapLibre non-fatal error:', e.error.message);
      }
    });

    map.current.on('click', (e) => {
      setClickedCoord({ lat: e.lngLat.lat, lon: e.lngLat.lng, x: e.point.x, y: e.point.y });
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, [lat, lng, zoom]);

  const checkWindAvailable = useCallback(async () => {
    try {
      const res = await fetch('/api/wind_texture?time=0&metadata=true');
      setIsWindAvailable(res.ok);
    } catch {
      setIsWindAvailable(false);
    }
  }, []);

  const fetchCogManifest = useCallback(async () => {
    try {
      const res = await fetch('/api/cog_manifest');
      const data = await res.json();
      cogManifestRef.current = data.variables ?? {};
      if (map.current && mapLoaded && data.bounds) {
        const [lon0, lat0, lon1, lat1] = data.bounds;
        map.current.fitBounds([lon0, lat0, lon1 < lon0 ? lon1 + 360 : lon1, lat1], { padding: 60, maxZoom: 9, duration: 1400 });
      }
    } catch (err) { console.warn(err); }
  }, [mapLoaded]);

  const pollEtlUntilDone = useCallback(() => {
    const poll = async (attempt = 0) => {
      if (attempt > 120) return;
      try {
        const res = await fetch('/api/etl/status');
        const status: EtlStatus = await res.json();
        if (status.running) {
          window.setTimeout(() => poll(attempt + 1), 3000);
          return;
        }
        if (status.files_created > 0) {
          showToast(`COG 轉檔完成（${status.files_created} 檔）`, 'success');
          fetchCogManifest();
          setDataRefreshKey((k) => k + 1);
        } else if (status.last_error) {
          showToast('COG 轉檔失敗，已改用動態圖磚', 'error');
        }
      } catch {
        /* ignore poll errors */
      }
    };
    poll();
  }, [fetchCogManifest, showToast]);

  useEffect(() => {
    fetch('/api/variables')
      .then(res => res.json())
      .then((data: VariableInfo[]) => {
        setVariables(data);
        const selected = data.find((variable) => variable.id === selectedVariable);
        if (selected?.available === false) {
          const fallback = data.find((variable) => variable.available !== false);
          if (fallback) setSelectedVariable(fallback.id);
        }
      })
      .catch(console.error);
    fetchCogManifest();
    checkWindAvailable();
  }, [fetchCogManifest, checkWindAvailable, selectedVariable, dataRefreshKey]);

  useEffect(() => {
    if (!mapLoaded || !map.current) return;
    setIsDataLoading(true);

    let active = true;

    if (showWind && isWindAvailable && windLayer) {
      windLayer.loadWindData(currentTimeIndex, selectedLevel).then(() => {
        if (active) windLayer.start();
      }).catch(() => {
        if (active) {
          showToast('風場載入失敗，功能暫停', 'error');
          setShowWind(false);
        }
      });
    } else if (windLayer) {
      windLayer.stop();
    }

    const bgVariable = selectedVariable;
    const statsUrl = `/api/variable_stats?time=${currentTimeIndex}&variable=${bgVariable}&level=${selectedLevel}`;

    const applyWithStats = (stats: VariableStats) => {
      if (!active || !map.current) return;
      const [rawMin, rawMax] = stats.valueRange;
      const vmin = selectedVariable === 'PSFC' ? 980 : (selectedVariable === 'T2' ? -20 : rawMin);
      const vmax = selectedVariable === 'PSFC' ? 1030 : (selectedVariable === 'T2' ? 40 : rawMax);
      setValueRange([vmin, vmax]);
      setLegendColormap(stats.colormap ?? 'viridis');

      removeLayerAndSource('weather-raster-layer', 'weather-raster-source');
      const paths = selectedLevel === 0 ? cogManifestRef.current[bgVariable] : undefined;
      const colormap = (stats.colormap ?? 'viridis').toLowerCase();

      if (paths && paths.length > 0) {
        const params = new URLSearchParams({
          url: paths[Math.min(currentTimeIndex, paths.length - 1)],
          rescale: `${vmin},${vmax}`,
          colormap_name: colormap,
          return_mask: 'true',
        });
        map.current!.addSource('weather-raster-source', {
          type: 'raster',
          tiles: [`/tiles/cog/tiles/WebMercatorQuad/{z}/{x}/{y}?${params}`],
          tileSize: 256,
          minzoom: 0,
          maxzoom: 12,
        });
      } else {
        const params = new URLSearchParams({
          variable: bgVariable,
          time: String(currentTimeIndex),
          vmin: String(vmin),
          vmax: String(vmax),
          level: String(selectedLevel),
        });
        map.current!.addSource('weather-raster-source', {
          type: 'raster',
          tiles: [`/api/tiles/{z}/{x}/{y}?${params}`],
          tileSize: 256,
          minzoom: 0,
          maxzoom: 12,
        });
        if (!fallbackToastShownRef.current && selectedLevel === 0) {
          showToast('COG 未就緒，使用動態圖磚渲染', 'info');
          fallbackToastShownRef.current = true;
        }
      }

      map.current!.addLayer(
        { id: 'weather-raster-layer', type: 'raster', source: 'weather-raster-source', paint: { 'raster-opacity': layerOpacity, 'raster-resampling': 'linear' } },
        map.current.getLayer('wind-particles') ? 'wind-particles' : undefined
      );
      ensureWindOnTop();
      setIsDataLoading(false);
    };

    const cached = statsCacheRef.current.get(statsUrl);
    if (cached) applyWithStats(cached);
    else {
      fetch(statsUrl).then(res => res.json()).then(data => {
        if (!active) return;
        if (data.error) throw new Error(data.error);
        statsCacheRef.current.set(statsUrl, data);
        applyWithStats(data);
      }).catch(() => {
        if (active) {
          setIsDataLoading(false);
          showToast('資料載入失敗', 'error');
        }
      });
    }

    return () => {
      active = false;
    };
  }, [currentTimeIndex, selectedVariable, selectedLevel, mapLoaded, windLayer, showWind, isWindAvailable, dataRefreshKey, layerOpacity, showToast, ensureWindOnTop]);

  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    let active = true;

    if (map.current.getLayer('contour-labels')) map.current.removeLayer('contour-labels');
    removeLayerAndSource('contour-layer', 'contour-source');

    if (!showContours) return;

    let contourVar = 'PSFC';
    if (selectedVariable === 'T2' || selectedVariable === 'T_LEV') {
      contourVar = selectedVariable;
    } else if (selectedVariable === 'P_HYD') {
      contourVar = 'P_HYD';
    } else if (selectedVariable === 'PSFC') {
      contourVar = 'PSFC';
    }
    fetch(`/api/contours?variable=${contourVar}&time=${currentTimeIndex}&level=${selectedLevel}`)
      .then(res => res.json())
      .then((data: FeatureCollection) => {
        if (!active || !map.current) return;

        if (map.current.getSource('contour-source')) {
          if (map.current.getLayer('contour-labels')) map.current.removeLayer('contour-labels');
          removeLayerAndSource('contour-layer', 'contour-source');
        }

        map.current.addSource('contour-source', { type: 'geojson', data });
        map.current.addLayer(
          { id: 'contour-layer', type: 'line', source: 'contour-source', paint: { 'line-color': 'rgba(255,255,255,0.3)', 'line-width': 1 } },
          map.current.getLayer('wind-particles') ? 'wind-particles' : undefined
        );
        map.current.addLayer(
          { id: 'contour-labels', type: 'symbol', source: 'contour-source', layout: { 'symbol-placement': 'line', 'text-field': ['get', 'value'], 'text-size': 10 }, paint: { 'text-color': '#fff', 'text-halo-color': 'rgba(0,0,0,0.5)', 'text-halo-width': 1 } },
          map.current.getLayer('wind-particles') ? 'wind-particles' : undefined
        );
        ensureWindOnTop();
      });

    return () => {
      active = false;
    };
  }, [mapLoaded, currentTimeIndex, selectedVariable, selectedLevel, showContours, ensureWindOnTop]);

  useEffect(() => {
    if (!mapLoaded || !map.current) return;
    let lastProbe = 0;
    const handleMouseMove = (e: maplibregl.MapMouseEvent) => {
      setHoverPos({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      const now = Date.now();
      if (now - lastProbe < 150) return;
      lastProbe = now;
      const targetVar = selectedVariable === 'WIND' ? 'WSPD' : selectedVariable;
      fetch(`/api/probe?lat=${e.lngLat.lat}&lon=${e.lngLat.lng}&variable=${targetVar}&time=${currentTimeIndex}&level=${selectedLevel}`)
        .then(res => res.json()).then(data => { if (!data.error) setHoverData(data); });
    };
    map.current.on('mousemove', handleMouseMove);
    map.current.on('mouseleave', () => { setHoverPos(null); setHoverData(null); });
    return () => { map.current?.off('mousemove', handleMouseMove); };
  }, [mapLoaded, selectedVariable, selectedLevel, currentTimeIndex]);

  useEffect(() => { if (windLayer) windLayer.setParams({ fadeOpacity: windFadeOpacity, speedFactor: windSpeedFactor, particleSize: windParticleSize }); }, [windLayer, windFadeOpacity, windSpeedFactor, windParticleSize]);
  useEffect(() => { if (windLayer) windLayer.setColorScheme(windColorScheme); }, [windLayer, windColorScheme]);

  const legendVar = variables.find(v => v.id === (selectedVariable === 'WIND' ? 'WSPD' : selectedVariable));

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh' }}>
      <DataInspector
        lat={hoverPos?.lat ?? null} lon={hoverPos?.lon ?? null}
        value={hoverData?.value ?? null}
        direction={hoverData?.direction ?? null}
        units={hoverData?.units ?? ''}
        variableName={legendVar?.name || ''}
      />
      <ForecastStatus
        currentTimeIndex={currentTimeIndex}
        timePointCount={timePointCount}
        selectedVariableName={legendVar?.name || selectedVariable}
        refreshKey={dataRefreshKey}
      />
      <LoadingOverlay isLoading={isDataLoading} message="載入數據中..." />
      <DataFileSelector onFileChange={() => {
        statsCacheRef.current.clear();
        fallbackToastShownRef.current = false;
        setDataRefreshKey((k) => k + 1);
        fetchCogManifest();
        pollEtlUntilDone();
        onDataFileChange?.();
      }} />
      <SearchBar onCoordinates={(lt, ln) => map.current?.flyTo({ center: [ln, lt], zoom: 8 })} />
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
      {variables.length > 0 && (
        <>
          <LayerPanel
            variables={variables} selectedVariable={selectedVariable} onVariableChange={handleVariableChange}
            showWind={showWind} onToggleWind={setShowWind} isWindAvailable={isWindAvailable}
            showContours={showContours} onToggleContours={setShowContours}
            layerOpacity={layerOpacity} onOpacityChange={setLayerOpacity}
            selectedLevel={selectedLevel} onLevelChange={setSelectedLevel}
          />
          <ColorLegend variable={selectedVariable} variableName={legendVar?.name || ''} units={legendVar?.units || ''} valueRange={valueRange} colormap={legendColormap} />
        </>
      )}
      <WindControls visible={showWind && isWindAvailable} fadeOpacity={windFadeOpacity} speedFactor={windSpeedFactor} particleSize={windParticleSize} colorScheme={windColorScheme} onFadeOpacityChange={setWindFadeOpacity} onSpeedFactorChange={setWindSpeedFactor} onParticleSizeChange={setWindParticleSize} onColorSchemeChange={setWindColorScheme} />
      <ExportButton mapRef={map} getWindCanvas={() => windLayer?.getCanvas() || null} />
      {clickedCoord && <CoordinatePopup lat={clickedCoord.lat} lon={clickedCoord.lon} x={clickedCoord.x} y={clickedCoord.y} variable={selectedVariable} timeIndex={currentTimeIndex} level={selectedLevel} onClose={() => setClickedCoord(null)} onCopy={() => { navigator.clipboard.writeText(`${clickedCoord.lat}, ${clickedCoord.lon}`); showToast('座標已複製', 'success'); }} />}
    </div>
  );
};

export default MapView;
