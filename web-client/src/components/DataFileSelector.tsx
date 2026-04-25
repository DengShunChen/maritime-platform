import React, { useState, useEffect } from 'react';
import './DataFileSelector.css';

interface NetCDFFile {
  filename: string;
  path: string;
  domain: string;
  date: string;
  size_mb: number;
  is_current: boolean;
}

interface DataFileSelectorProps {
  onFileChange?: () => void;
}

export const DataFileSelector: React.FC<DataFileSelectorProps> = ({ onFileChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [files, setFiles] = useState<NetCDFFile[]>([]);
  const [currentFile, setCurrentFile] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  // Fetch available files
  const fetchFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/netcdf_files');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setFiles(data.files || []);
      setCurrentFile(data.current || '');
    } catch (err) {
      setError('無法載入檔案列表');
      console.error('Error fetching NetCDF files:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch on mount and when panel opens
  useEffect(() => {
    if (isOpen) {
      fetchFiles();
    }
  }, [isOpen]);

  // Select a file
  const handleSelectFile = async (filepath: string) => {
    if (filepath === currentFile) return;
    
    setSwitching(true);
    setError(null);
    try {
      const response = await fetch('/api/netcdf_files/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filepath })
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setCurrentFile(data.current);
      
      // Update file list to reflect new selection
      setFiles(prev => prev.map(f => ({
        ...f,
        is_current: f.path === data.current
      })));
      
      // Notify parent to refresh data
      onFileChange?.();
      
      // Close panel after successful switch
      setTimeout(() => setIsOpen(false), 500);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : '切換檔案失敗');
      console.error('Error selecting NetCDF file:', err);
    } finally {
      setSwitching(false);
    }
  };

  // Get display info for current file
  const currentDomain = files.find(f => f.is_current)?.domain || '';

  return (
    <div className="data-file-selector">
      <button 
        className={`file-selector-toggle ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title="選擇資料檔案"
      >
        <span className="toggle-icon">📂</span>
        <span className="toggle-label">
          {currentDomain && <span className="domain-badge">{currentDomain}</span>}
          資料檔案
        </span>
        <span className="toggle-chevron">{isOpen ? '▼' : '▶'}</span>
      </button>

      {isOpen && (
        <div className="file-selector-panel">
          <div className="panel-header">
            <h3>選擇 WRF 資料檔案</h3>
            <button className="refresh-btn" onClick={fetchFiles} disabled={loading}>
              🔄
            </button>
          </div>

          {loading && (
            <div className="panel-loading">載入中...</div>
          )}

          {error && (
            <div className="panel-error">{error}</div>
          )}

          {!loading && files.length === 0 && (
            <div className="panel-empty">沒有找到 NetCDF 檔案</div>
          )}

          <div className="file-list">
            {files.map((file) => (
              <button
                key={file.path}
                className={`file-item ${file.is_current ? 'current' : ''} ${switching ? 'disabled' : ''}`}
                onClick={() => handleSelectFile(file.path)}
                disabled={switching || file.is_current}
              >
                <div className="file-info">
                  <span className="file-domain">{file.domain}</span>
                  <span className="file-date">{file.date}</span>
                </div>
                <div className="file-meta">
                  <span className="file-size">{file.size_mb} MB</span>
                  {file.is_current && <span className="current-badge">✓ 使用中</span>}
                </div>
              </button>
            ))}
          </div>

          {switching && (
            <div className="switching-overlay">
              <div className="switching-spinner" />
              <span>切換中...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
