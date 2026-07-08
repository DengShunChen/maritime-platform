/** Shared API response types for frontend/backend contract */

export interface VariableInfo {
  id: string;
  name: string;
  description?: string;
  units: string;
  colormap?: string;
}

export interface VariableStats {
  valueRange: [number, number];
  bounds?: [number, number, number, number];
  colormap?: string;
  units?: string;
  name?: string;
  error?: string;
}

export interface WindTextureMetadata {
  uMin: number;
  uMax: number;
  vMin: number;
  vMax: number;
  width: number;
  height: number;
  bounds: [number, number, number, number];
}

export interface ProbeResult {
  value: number;
  units: string;
  variable: string;
  lat: number;
  lon: number;
  direction?: number;
  error?: string;
}

export interface CogManifest {
  variables: Record<string, string[]>;
  bounds?: [number, number, number, number];
}

export interface EtlStatus {
  running: boolean;
  last_path: string | null;
  last_error: string | null;
  files_created: number;
}

