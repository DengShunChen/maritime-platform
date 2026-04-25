import { BitmapLayer } from '@deck.gl/layers';
import type { Color } from '@deck.gl/core';

// Old interface for backward compatibility (if needed for tooltips later)
interface WeatherDataPoint {
  lon: number;
  lat: number;
  value: number;
}

// New interface for BitmapLayer
interface BitmapWeatherLayerProps {
  imageUrl: string;
  bounds: [number, number, number, number]; // [left, bottom, right, top]
  variable: string;
  opacity?: number;
}

// Legacy interface (kept for reference)
interface DeckGLWeatherLayerProps {
  data: WeatherDataPoint[];
  variable: string;
  colorScheme: string;
  opacity?: number;
  radiusPixels?: number;
}

// Colormap definitions (kept for ColorLegend component)
const COLOR_SCHEMES: Record<string, Color[]> = {
  'viridis': [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37]
  ],
  'RdYlBu_r': [
    [49, 54, 149],
    [69, 117, 180],
    [171, 217, 233],
    [254, 224, 144],
    [253, 174, 97],
    [244, 109, 67],
    [215, 48, 39]
  ],
  'YlGnBu': [
    [255, 255, 217],
    [237, 248, 177],
    [199, 233, 180],
    [127, 205, 187],
    [65, 182, 196],
    [29, 145, 192],
    [34, 94, 168]
  ],
  'RdBu_r': [
    [33, 102, 172],
    [67, 147, 195],
    [146, 197, 222],
    [247, 247, 247],
    [244, 165, 130],
    [214, 96, 77],
    [178, 24, 43]
  ],
  'gist_ncar': [
    [0, 0, 128],
    [0, 128, 255],
    [0, 255, 255],
    [0, 255, 0],
    [255, 255, 0],
    [255, 128, 0],
    [255, 0, 0]
  ]
};

/**
 * Creates a BitmapLayer for smooth WebGL texture-based weather visualization.
 * Uses GPU linear interpolation for Windy.com-style smooth gradients.
 */
export function createWeatherBitmapLayer(props: BitmapWeatherLayerProps) {
  const {
    imageUrl,
    bounds,
    variable,
    opacity = 0.8
  } = props;

  return new BitmapLayer({
    id: `weather-bitmap-${variable}`,
    image: imageUrl,
    bounds: bounds,
    opacity,
    // textureParameters for smooth linear interpolation
    textureParameters: {
      minFilter: 'linear',
      magFilter: 'linear',
      mipmapFilter: 'linear',
      addressModeU: 'clamp-to-edge',
      addressModeV: 'clamp-to-edge'
    },
    pickable: false
  });
}

export { COLOR_SCHEMES };
export type { WeatherDataPoint, DeckGLWeatherLayerProps, BitmapWeatherLayerProps };
