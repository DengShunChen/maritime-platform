import React, { useEffect, useMemo, useState } from 'react';
import './ForecastStatus.css';
import type { ModelSummary, VersionInfo } from '../types/api';

interface ForecastStatusProps {
  currentTimeIndex: number;
  timePointCount: number;
  selectedVariableName: string;
  refreshKey?: number;
}

export const ForecastStatus: React.FC<ForecastStatusProps> = ({
  currentTimeIndex,
  timePointCount,
  selectedVariableName,
  refreshKey = 0
}) => {
  const [summary, setSummary] = useState<ModelSummary | null>(null);
  const [version, setVersion] = useState<VersionInfo | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [summaryRes, versionRes] = await Promise.all([
          fetch('/api/model_summary'),
          fetch('/api/version')
        ]);
        const summaryData = await summaryRes.json();
        const versionData = await versionRes.json();
        if (active) {
          if (!summaryData.error) setSummary(summaryData);
          if (!versionData.error) setVersion(versionData);
        }
      } catch (err) {
        console.warn('Failed to load forecast status:', err);
      }
    };

    load();
    const timer = window.setInterval(load, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refreshKey]);

  const domainText = useMemo(() => {
    if (!summary?.bounds) return 'domain --';
    const [lon0, lat0, lon1, lat1] = summary.bounds;
    return `${lat0.toFixed(1)}-${lat1.toFixed(1)}N / ${lon0.toFixed(1)}-${lon1.toFixed(1)}E`;
  }, [summary]);

  const progressText = `${Math.min(currentTimeIndex + 1, Math.max(timePointCount, 1))}/${Math.max(timePointCount, 1)}`;
  const etlRunning = summary?.etl?.running ?? false;
  const hasCog = (summary?.cogTilesReady ?? 0) > 0;
  const marineCount = summary?.marineVariables ?? 0;
  const shortSha = version?.gitSha && version.gitSha !== 'unknown'
    ? version.gitSha.slice(0, 7)
    : '';
  const versionText = version
    ? [version.version, shortSha].filter(Boolean).join(' ')
    : 'version --';
  const versionTitle = version
    ? `${version.version} ${version.gitSha} ${version.buildDate}`.trim()
    : undefined;

  return (
    <div className="forecast-status glass-panel">
      <div className="forecast-brand">
        <span className="brand-mark">MP</span>
        <div className="brand-copy">
          <span className="brand-title">Maritime Forecast</span>
          <span className="brand-subtitle">{summary?.file ?? version?.dataset ?? 'WRF output'}</span>
        </div>
      </div>

      <div className="status-grid">
        <div className="status-cell">
          <span className="status-label">Valid</span>
          <span className="status-value">{progressText}</span>
        </div>
        <div className="status-cell">
          <span className="status-label">Layer</span>
          <span className="status-value">{selectedVariableName || '--'}</span>
        </div>
        <div className="status-cell wide">
          <span className="status-label">Domain</span>
          <span className="status-value">{domainText}</span>
        </div>
      </div>

      <div className="pipeline-row">
        <span className={`pipeline-pill ${hasCog ? 'ready' : 'fallback'}`}>
          {hasCog ? 'COG ready' : 'dynamic tiles'}
        </span>
        <span className={`pipeline-pill ${etlRunning ? 'running' : 'ready'}`}>
          {etlRunning ? 'ETL running' : 'ETL idle'}
        </span>
        <span className={`pipeline-pill ${marineCount > 0 ? 'ready' : 'muted'}`}>
          Sea {marineCount > 0 ? `${marineCount} vars` : 'pending'}
        </span>
        <span className="pipeline-pill version" title={versionTitle}>
          {versionText}
        </span>
      </div>
    </div>
  );
};
