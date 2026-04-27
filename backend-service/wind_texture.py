"""
Wind Texture Encoding Module

Encodes WRF NetCDF U10/V10 wind components into PNG textures for WebGL rendering.
This follows the Windy.com / mapbox/webgl-wind approach where:
- R channel = U component (normalized 0-255)
- G channel = V component (normalized 0-255)
- B channel = reserved (0)
- A channel = 255 (fully opaque)
"""

import numpy as np
from PIL import Image
import io
import io
from typing import Tuple, Dict, Any


def create_coordinate_texture(
    lons: np.ndarray,
    lats: np.ndarray,
    lon_range: Tuple[float, float] = None,
    lat_range: Tuple[float, float] = None
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Encode Longitude and Latitude arrays into a raw RGBA binary array.
    """
    # Handle NaN
    lons = np.nan_to_num(lons, nan=0.0)
    lats = np.nan_to_num(lats, nan=0.0)
    
    # Determine ranges
    if lon_range is None:
        min_lon, max_lon = float(np.min(lons)), float(np.max(lons))
    else:
        min_lon, max_lon = lon_range
        
    if lat_range is None:
        min_lat, max_lat = float(np.min(lats)), float(np.max(lats))
    else:
        min_lat, max_lat = lat_range
        
    # range values
    lon_span = max(max_lon - min_lon, 0.001)
    lat_span = max(max_lat - min_lat, 0.001)
    
    # Normalize to 0-65535 (16-bit)
    lon_norm = ((lons - min_lon) / lon_span * 65535).clip(0, 65535).astype(np.uint16)
    lat_norm = ((lats - min_lat) / lat_span * 65535).clip(0, 65535).astype(np.uint16)
    
    height, width = lons.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Encode Longitude (High/Low bytes)
    rgba[:, :, 0] = (lon_norm >> 8) & 0xFF  # R = High
    rgba[:, :, 1] = lon_norm & 0xFF         # G = Low
    
    # Encode Latitude (High/Low bytes)
    rgba[:, :, 2] = (lat_norm >> 8) & 0xFF  # B = High
    rgba[:, :, 3] = lat_norm & 0xFF         # A = Low
    
    metadata = {
        'min_lon': min_lon,
        'max_lon': max_lon,
        'min_lat': min_lat,
        'max_lat': max_lat,
        'width': width,
        'height': height
    }
    return rgba.tobytes(), metadata


def encode_wind_to_png(
    u_data: np.ndarray,
    v_data: np.ndarray,
    u_range: Tuple[float, float] = None,
    v_range: Tuple[float, float] = None
) -> Tuple[io.BytesIO, Dict[str, Any]]:
    """
    Encode U/V wind components into a PNG image.
    
    Args:
        u_data: 2D array of U wind component (m/s)
        v_data: 2D array of V wind component (m/s)
        u_range: Optional (min, max) range for U normalization. Auto-calculated if None.
        v_range: Optional (min, max) range for V normalization. Auto-calculated if None.
    
    Returns:
        Tuple of (BytesIO containing PNG data, metadata dict)
    """
    # Handle NaN values
    u_data = np.nan_to_num(u_data, nan=0.0)
    v_data = np.nan_to_num(v_data, nan=0.0)
    
    # Calculate or use provided ranges
    if u_range is None:
        u_min, u_max = float(np.min(u_data)), float(np.max(u_data))
    else:
        u_min, u_max = u_range
    
    if v_range is None:
        v_min, v_max = float(np.min(v_data)), float(np.max(v_data))
    else:
        v_min, v_max = v_range
    
    # Avoid division by zero
    u_range_val = max(u_max - u_min, 0.001)
    v_range_val = max(v_max - v_min, 0.001)
    
    # Normalize to 0-255
    u_norm = ((u_data - u_min) / u_range_val * 255).clip(0, 255).astype(np.uint8)
    v_norm = ((v_data - v_min) / v_range_val * 255).clip(0, 255).astype(np.uint8)
    
    # Create RGBA image
    height, width = u_data.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = u_norm  # R = U
    rgba[:, :, 1] = v_norm  # G = V
    rgba[:, :, 2] = 0       # B = 0
    rgba[:, :, 3] = 255     # A = fully opaque
    
    # Convert to PIL Image and save to bytes
    img = Image.fromarray(rgba, mode='RGBA')
    
    # Use PNG compression for good quality/size balance
    buf = io.BytesIO()
    img.save(buf, format='PNG', compress_level=1)
    buf.seek(0)
    
    metadata = {
        'u_min': u_min,
        'u_max': u_max,
        'v_min': v_min,
        'v_max': v_max,
        'width': width,
        'height': height
    }
    
    return buf, metadata


def create_color_ramp(colormap_name: str = 'viridis', steps: int = 256) -> io.BytesIO:
    """
    Create a 1D color ramp texture for wind speed visualization.
    
    Args:
        colormap_name: Matplotlib colormap name
        steps: Number of color steps
    
    Returns:
        BytesIO containing PNG data (steps x 1 pixels)
    """
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    
    try:
        cmap = cm.get_cmap(colormap_name)
    except ValueError:
        cmap = cm.get_cmap('viridis')
    
    # Create 1D color ramp
    rgba = np.zeros((1, steps, 4), dtype=np.uint8)
    for i in range(steps):
        r, g, b, a = cmap(i / (steps - 1))
        rgba[0, i, 0] = int(r * 255)
        rgba[0, i, 1] = int(g * 255)
        rgba[0, i, 2] = int(b * 255)
        rgba[0, i, 3] = int(a * 255)
    
    img = Image.fromarray(rgba[0].reshape(1, steps, 4), mode='RGBA')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return buf
