from flask import Flask, jsonify, request, make_response, send_file
import logging
import xarray as xr
import numpy as np
import io
import matplotlib.cm
import matplotlib.colors
import os
import math
from datetime import datetime, timedelta
from PIL import Image, ImageFilter
import pandas as pd
import datashader as dsh
import datashader.transfer_functions as tf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from functools import lru_cache
try:
    import cfgrib
except ImportError:
    pass

from models import TimePoint, SpatialGrid, SlpData
from models import TimePoint, SpatialGrid, SlpData
from wind_texture import encode_wind_to_png, create_color_ramp, create_coordinate_texture
from convert_to_grib import convert_to_grib2

# Variable metadata configuration
VARIABLE_CONFIG = {
    'PSFC': {
        'name': '表面氣壓',
        'description': 'Surface Pressure',
        'units': 'hPa',
        'colormap': 'viridis',
        'scale': 0.01,  # Pa to hPa
        'db_field': 'slp'  # For now, map to existing field
    },
    'T2': {
        'name': '2米溫度',
        'description': '2m Temperature',
        'units': '°C',
        'colormap': 'RdYlBu_r',
        'offset': -273.15,  # K to C
        'db_field': None  # Will need new field
    },
    'RAINC': {
        'name': '累積對流降水',
        'description': 'Accumulated Cumulus Precipitation',
        'units': 'mm',
        'colormap': 'YlGnBu',
        'db_field': None
    },
    'RAINNC': {
        'name': '累積網格降水',
        'description': 'Accumulated Grid Scale Precipitation',
        'units': 'mm',
        'colormap': 'YlGnBu',
        'db_field': None
    },
    'U10': {
        'name': '10米 U 風分量',
        'description': '10m U-Wind Component',
        'units': 'm/s',
        'colormap': 'RdBu_r',
        'db_field': None
    },
    'V10': {
        'name': '10米 V 風分量',
        'description': '10m V-Wind Component',
        'units': 'm/s',
        'colormap': 'RdBu_r',
        'db_field': None
    },
    'REFD_MAX': {
        'name': '最大雷達反射率',
        'description': 'Maximum Radar Reflectivity',
        'units': 'dBZ',
        'colormap': 'gist_ncar',
        'db_field': None
    },
    'WSPD': {
        'name': '風速',
        'description': 'Wind Speed',
        'units': 'm/s',
        'colormap': 'viridis',
        'db_field': None
    }
}

app = Flask(__name__)


# Configure logging for the Flask app to output to stdout
app.logger.setLevel(logging.DEBUG)

# Database connection string
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/maritime_db")
NETCDF_DATA_DIR = os.getenv("NETCDF_DATA_DIR", "data")
NETCDF_PATH = os.getenv("NETCDF_PATH", "data/wrfout_v2_Lambert.grib2")

# Current selected NetCDF file (can be changed at runtime)
_CURRENT_NETCDF = {
    "path": NETCDF_PATH
}

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

_DATASET_CACHE = {
    "path": None,
    "mtime": None,
    "ds": None
}

_GRID_CACHE = {
    "path": None,
    "mtime": None,
    "x_flat": None,
    "y_flat": None,
    "shape": None
}


def get_current_netcdf_path():
    """Get the current NetCDF file path."""
    return _CURRENT_NETCDF["path"]


def set_current_netcdf_path(path: str):
    """Set the current NetCDF file path and clear caches."""
    global _DATASET_CACHE, _GRID_CACHE
    
    # Close existing dataset if any
    if _DATASET_CACHE["ds"] is not None:
        try:
            _DATASET_CACHE["ds"].close()
        except Exception:
            pass
    
    # Clear caches
    _DATASET_CACHE = {"path": None, "mtime": None, "ds": None}
    _GRID_CACHE = {"path": None, "mtime": None, "x_flat": None, "y_flat": None, "shape": None}
    
    # Set new path
    _CURRENT_NETCDF["path"] = path
    app.logger.info(f"Switched NetCDF file to: {path}")


def get_dataset():
    """Return a cached xarray dataset (reload if file changed)."""
    path = get_current_netcdf_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        raise FileNotFoundError(f"NetCDF file not found: {path}")

    if _DATASET_CACHE["ds"] is None or _DATASET_CACHE["path"] != path or _DATASET_CACHE["mtime"] != mtime:
        if _DATASET_CACHE["ds"] is not None:
            try:
                _DATASET_CACHE["ds"].close()
            except Exception:
                pass
        if path.endswith('.grib2') or path.endswith('.grb2'):
             # GRIB2 files often have multiple "hypercubes" (steps, vertical levels).
             # We must load them separately and merge.
             datasets = []
             try:
                 # 1. Height Above Ground (T2, U10, V10)
                 ds_h = xr.open_dataset(path, engine="cfgrib", backend_kwargs={'filter_by_keys': {'typeOfLevel': 'heightAboveGround'}, 'indexpath': ''})
                 datasets.append(ds_h)
             except Exception:
                 pass

             try:
                 # 2. Surface (PSFC)
                 ds_s = xr.open_dataset(path, engine="cfgrib", backend_kwargs={'filter_by_keys': {'typeOfLevel': 'surface'}, 'indexpath': ''})
                 datasets.append(ds_s)
             except Exception:
                 pass
                 
             try:
                 # 3. Mean Sea Level (MSLP)
                 ds_m = xr.open_dataset(path, engine="cfgrib", backend_kwargs={'filter_by_keys': {'typeOfLevel': 'meanSea'}, 'indexpath': ''})
                 datasets.append(ds_m)
             except Exception:
                 pass
             
             if datasets:
                 _DATASET_CACHE["ds"] = xr.merge(datasets)
             else:
                 # Fallback to default if manual parts failed (e.g. simple 1-var file)
                 _DATASET_CACHE["ds"] = xr.open_dataset(path, engine="cfgrib", backend_kwargs={'indexpath': ''})
        else:
             _DATASET_CACHE["ds"] = xr.open_dataset(path, engine="netcdf4")
        
        _DATASET_CACHE["path"] = path
        _DATASET_CACHE["mtime"] = mtime

    return _DATASET_CACHE["ds"]


def _lonlat_to_webmercator(lon_deg, lat_deg):
    """Convert lon/lat (degrees) to WebMercator meters."""
    r_major = 6378137.0
    lon_rad = np.deg2rad(lon_deg)
    lat_rad = np.deg2rad(np.clip(lat_deg, -85.05112878, 85.05112878))
    x = r_major * lon_rad
    y = r_major * np.log(np.tan((math.pi / 4.0) + (lat_rad / 2.0)))
    return x, y


def _webmercator_to_lonlat(x, y):
    """Convert WebMercator meters to lon/lat (degrees)."""
    r_major = 6378137.0
    lon_deg = np.rad2deg(x / r_major)
    lat_rad = (2.0 * np.arctan(np.exp(y / r_major))) - (math.pi / 2.0)
    lat_deg = np.rad2deg(lat_rad)
    return lon_deg, lat_deg


def _tile_bounds_webmercator(z, x, y):
    """Return WebMercator bounds (meters) for a slippy map tile."""
    r_major = 6378137.0
    world_extent = 2.0 * math.pi * r_major
    tiles = 2 ** z
    tile_size = 256
    res = world_extent / (tiles * tile_size)
    minx = -world_extent / 2.0 + (x * tile_size * res)
    maxx = -world_extent / 2.0 + ((x + 1) * tile_size * res)
    maxy = world_extent / 2.0 - (y * tile_size * res)
    miny = world_extent / 2.0 - ((y + 1) * tile_size * res)
    return minx, miny, maxx, maxy


def _get_grid_cache(ds):
    """Cache projected grid coordinates in WebMercator meters."""
    path = get_current_netcdf_path()
    mtime = os.path.getmtime(path)
    lons, lats = _get_coords(ds, 0)
    shape = lons.shape

    if (_GRID_CACHE["x_flat"] is None
        or _GRID_CACHE["path"] != path
        or _GRID_CACHE["mtime"] != mtime
        or _GRID_CACHE["shape"] != shape):
        x, y = _lonlat_to_webmercator(lons, lats)
        _GRID_CACHE["x_flat"] = x.ravel()
        _GRID_CACHE["y_flat"] = y.ravel()
        _GRID_CACHE["path"] = path
        _GRID_CACHE["mtime"] = mtime
        _GRID_CACHE["shape"] = shape

    return _GRID_CACHE["x_flat"], _GRID_CACHE["y_flat"], shape


def _map_variable(ds, var_id):
    """Map generic variable ID to dataset-specific name (NetCDF vs GRIB)."""
    if var_id in ds:
        return var_id
    
    # Common GRIB2 mappings (cfgrib styles)
    grib_map = {
        'PSFC': ['sp', 'msl'], # Surface pressure
        'T2': ['2t', 't2m', 't'],   # 2m Temperature
        'U10': ['10u', 'u10', 'u'], # 10m U Wind
        'V10': ['10v', 'v10', 'v'], # 10m V Wind
        'RAINC': ['tp'],       # Total precip?
    }
    
    if var_id in grib_map:
        for candidate in grib_map[var_id]:
            if candidate in ds:
                return candidate
    return None

def _get_time_slice(ds, var, time_index):
    """Helper to slice a variable by time/step dimension."""
    dims = ds[var].dims
    if 'Time' in dims:
        return ds[var].isel(Time=time_index)
    elif 'time' in dims:
        return ds[var].isel(time=time_index)
    elif 'step' in dims:
        return ds[var].isel(step=time_index)
    else:
        # Assume static or single slice
        return ds[var]

def _get_coords(ds, time_index=0):
    """Return lon, lat arrays handling naming and time slicing."""
    if 'XLONG' in ds:
        x_name, y_name = 'XLONG', 'XLAT'
    else:
        x_name, y_name = 'longitude', 'latitude'
        
    lons = _get_time_slice(ds, x_name, time_index).values
    lats = _get_time_slice(ds, y_name, time_index).values
    
    # If 1D arrays (GRIB2 regular_ll), meshgrid them to 2D
    if lons.ndim == 1 and lats.ndim == 1:
        lons, lats = np.meshgrid(lons, lats)
        
    return lons, lats

def _get_num_times(ds):
    """Helper to get number of time steps safely."""
    for dim in ['Time', 'time', 'step']:
        if dim in ds.sizes:
            return ds.sizes[dim]
    return 1

def _get_grid_slice(ds, min_lon, max_lon, min_lat, max_lat):
    """
    Calculate start/end indices for regular Lat/Lon grid subset.
    Returns (lat_slice, lon_slice) for use in .isel()
    """
    # Get 1D coordinate arrays (assuming regular_ll GRIB2)
    # GRIB2 from cfgrib usually has 'latitude' and 'longitude' 1D coords
    if 'latitude' in ds.coords and 'longitude' in ds.coords:
        lats = ds.coords['latitude'].values
        lons = ds.coords['longitude'].values
    elif 'XLAT' in ds.coords: 
        # NetCDF fallback (likely 2D, can't easily slice without logic, but we enforced GRIB2)
        # For simplicity, if not regular 1D, return full slice
        return slice(None), slice(None)
    else:
        return slice(None), slice(None)

    # Handle Longitude (0-360 or -180-180)
    # Our data seems to be 115 to 152
    
    # Find indices (searchsorted requires sorted array)
    # Lats are usually descending (90 to -90) or ascending. 
    # check order
    lat_increasing = lats[1] > lats[0]
    lon_increasing = lons[1] > lons[0]

    # Add precision buffer
    pad = 0.1 
    
    if lon_increasing:
        lon_start = np.searchsorted(lons, min_lon - pad)
        lon_end = np.searchsorted(lons, max_lon + pad)
    else:
        # Should not happen for standard GRIB usually
        lon_start = 0; lon_end = len(lons)

    if lat_increasing:
        lat_start = np.searchsorted(lats, min_lat - pad)
        lat_end = np.searchsorted(lats, max_lat + pad)
    else:
        # Descending lats (common in GRIB)
        # max_lat corresponds to lower index
        lat_start = np.searchsorted(lats[::-1], min_lat - pad)
        lat_end = np.searchsorted(lats[::-1], max_lat + pad)
        # Invert indices because we searched on reversed array
        N = len(lats)
        # Original indices: N - 1 - idx
        # Range becomes [N - lat_end, N - lat_start]
        t_start = N - lat_end
        t_end = N - lat_start
        lat_start = max(0, t_start)
        lat_end = min(N, t_end)

    # Clamp
    lon_start = max(0, min(lon_start, len(lons)-1))
    lon_end = max(0, min(lon_end, len(lons)))
    
    # Ensure range valid
    if lat_start >= lat_end: lat_end = lat_start + 1
    if lon_start >= lon_end: lon_end = lon_start + 1

    return slice(lat_start, lat_end), slice(lon_start, lon_end)


def _get_variable_data(ds, variable_id, time_index):
    """Return 2D data array for a variable and time index."""
    if variable_id == 'WSPD':
        # Special handling for derived wind speed
        u_name = _map_variable(ds, 'U10')
        v_name = _map_variable(ds, 'V10')
        
        if not u_name or not v_name:
             raise KeyError(f"Wind variables U10/V10 not found (candidates checked)")

        u = _get_time_slice(ds, u_name, time_index)
        v = _get_time_slice(ds, v_name, time_index)
        var_data = np.sqrt(u**2 + v**2)
        var_data = var_data.where(var_data < 500)
    else:
        real_var_name = _map_variable(ds, variable_id)
        if not real_var_name:
             raise KeyError(f"Variable {variable_id} not found in dataset")
        
        var_data = _get_time_slice(ds, real_var_name, time_index)

    if 'bottom_top' in var_data.dims:
        var_data = var_data.isel(bottom_top=0)

    return var_data.values


def _apply_scale_offset(values, var_config):
    if 'scale' in var_config:
        values = values * var_config['scale']
    if 'offset' in var_config:
        values = values + var_config['offset']
    return values


def _build_colormap(name, steps=256):
    try:
        cmap = matplotlib.cm.get_cmap(name)
    except Exception:
        cmap = matplotlib.cm.get_cmap('viridis')
    return [matplotlib.colors.rgb2hex(cmap(i / (steps - 1))) for i in range(steps)]



@app.route('/')
def hello_world():
    return jsonify(message="Hello from backend!")

@app.route('/netcdf_attributes')
def get_netcdf_attributes():
    try:
        ds_netcdf = get_dataset()
        attributes = ds_netcdf.attrs
        return jsonify(attributes)
    except Exception as e:
        app.logger.error(f"Error reading NetCDF attributes: {e}")
        return jsonify(error=f"Error reading NetCDF attributes: {e}"), 500

@app.route('/time_points')
def get_time_points():
    """
    Return list of time points from the NetCDF/GRIB2 file.
    Reads directly from the 'Times' variable (WRF datetime strings),
    'time'/'valid_time'/'step' (GRIB2), or falls back to 'XTIME' (model minutes).
    
    Returns: List of Unix timestamps (seconds since epoch)
    """
    try:
        ds = get_dataset()
        path = get_current_netcdf_path()
        is_grib = path.endswith('.grib2') or path.endswith('.grb2')
        
        app.logger.info(f"Extracting time points from: {path} (GRIB2: {is_grib})")
        
        # GRIB2-specific time extraction
        if is_grib:
            app.logger.debug(f"GRIB2 dataset dimensions: {list(ds.dims.keys())}")
            app.logger.debug(f"GRIB2 dataset coords: {list(ds.coords.keys())}")
            
            # Try common GRIB2 time coordinates
            for time_coord in ['time', 'valid_time', 'step']:
                if time_coord in ds.coords:
                    try:
                        time_values = ds.coords[time_coord].values
                        app.logger.info(f"Found GRIB2 time coordinate: '{time_coord}', values: {time_values}")
                        
                        time_stamps = []
                        # Handle different time formats
                        if hasattr(time_values, '__iter__') and not isinstance(time_values, (str, bytes)):
                            # Array of times
                            for tv in time_values:
                                if hasattr(tv, 'astype'):
                                    # numpy datetime64
                                    ts = int(pd.Timestamp(tv).timestamp())
                                else:
                                    ts = int(tv)
                                time_stamps.append(ts)
                        else:
                            # Single time value
                            if hasattr(time_values, 'astype'):
                                ts = int(pd.Timestamp(time_values).timestamp())
                            else:
                                ts = int(time_values)
                            time_stamps.append(ts)
                        
                        app.logger.info(f"Extracted {len(time_stamps)} time points from GRIB2")
                        app.logger.debug(f"First timestamp: {time_stamps[0]} ({datetime.fromtimestamp(time_stamps[0])})")
                        return jsonify(time_stamps)
                    except Exception as e:
                        app.logger.warning(f"Failed to parse GRIB2 time coordinate '{time_coord}': {e}")
                        continue
            
            # GRIB2 fallback: check dimensions for time/step count
            for dim_name in ['time', 'step', 'valid_time']:
                if dim_name in ds.dims:
                    num_times = ds.dims[dim_name]
                    app.logger.warning(f"GRIB2 time extraction failed, using dimension '{dim_name}' with {num_times} steps")
                    # Generate synthetic timestamps
                    base_time = datetime.now()
                    time_stamps = [int((base_time + timedelta(hours=i)).timestamp()) for i in range(num_times)]
                    app.logger.warning(f"Generated {len(time_stamps)} synthetic timestamps starting at {base_time}")
                    return jsonify(time_stamps)
        
        # Try to get time from 'Times' variable (WRF standard)
        if 'Times' in ds:
            # Times is stored as character array, need to decode
            times_raw = ds['Times'].values
            time_stamps = []
            for t in times_raw:
                # Handle both bytes and string
                if isinstance(t, bytes):
                    time_str = t.decode('utf-8')
                elif hasattr(t, 'tobytes'):
                    time_str = t.tobytes().decode('utf-8')
                else:
                    time_str = str(t)
                # WRF format: "2025-09-18_00:00:00"
                time_str = time_str.strip().replace('_', 'T')
                try:
                    dt = datetime.fromisoformat(time_str)
                    time_stamps.append(int(dt.timestamp()))
                except ValueError:
                    # Try alternative parsing
                    from dateutil import parser
                    dt = parser.parse(time_str.replace('_', ' '))
                    time_stamps.append(int(dt.timestamp()))
            app.logger.info(f"Extracted {len(time_stamps)} time points from WRF 'Times' variable")
            return jsonify(time_stamps)
        
        # Fallback: Try XTIME (minutes since simulation start)
        if 'XTIME' in ds:
            xtime = ds['XTIME'].values
            # Get simulation start time from global attributes
            start_date_str = ds.attrs.get('START_DATE', ds.attrs.get('SIMULATION_START_DATE', ''))
            if start_date_str:
                start_date_str = start_date_str.replace('_', 'T')
                base_dt = datetime.fromisoformat(start_date_str)
            else:
                # Default to first file timestamp if no attribute
                base_dt = datetime(2000, 1, 1)
            
            time_stamps = []
            for minutes in xtime:
                dt = base_dt + timedelta(minutes=float(minutes))
                time_stamps.append(int(dt.timestamp()))
            app.logger.info(f"Extracted {len(time_stamps)} time points from 'XTIME' variable")
            return jsonify(time_stamps)
        
        # Last fallback: use Time dimension indices
        num_times = ds.sizes.get('Time', 0)
        if num_times == 0:
            app.logger.warning("No time dimension found in dataset, returning empty array")
            return jsonify([])
        
        # Try to get start date from attributes
        start_date_str = ds.attrs.get('START_DATE', ds.attrs.get('SIMULATION_START_DATE', ''))
        if start_date_str:
            start_date_str = start_date_str.replace('_', 'T')
            base_dt = datetime.fromisoformat(start_date_str)
        else:
            base_dt = datetime.now()
            app.logger.warning(f"No start date attribute found, using current time: {base_dt}")
        
        # Assume hourly data if no time info
        time_stamps = []
        for i in range(num_times):
            dt = base_dt + timedelta(hours=i)
            time_stamps.append(int(dt.timestamp()))
        
        app.logger.warning(f"Using fallback: generated {len(time_stamps)} timestamps from Time dimension")
        return jsonify(time_stamps)
        
    except Exception as e:
        app.logger.error(f"Error reading time points from NetCDF: {e}", exc_info=True)
        return jsonify(error=f"Error reading time points: {e}"), 500



@app.route('/netcdf_files')
def list_netcdf_files():
    """
    List available NetCDF files in the data directory.
    Returns file info including name, domain, date, and file size.
    """
    try:
        files = []
        data_dir = NETCDF_DATA_DIR
        
        if not os.path.exists(data_dir):
            return jsonify(error=f"Data directory not found: {data_dir}"), 404
        
        # First pass: collect all files to identify pairs
        all_files = sorted(os.listdir(data_dir))
        grib_files = set(f for f in all_files if f.endswith('.grib2') or f.endswith('.grb2'))
        
        for filename in all_files:
            filepath = os.path.join(data_dir, filename)
            if not os.path.isfile(filepath):
                continue
                
            # Logic:
            # 1. If it's a GRIB2 file -> Show it
            # 2. If it's a NetCDF file AND its GRIB2 version does NOT exist -> Show it (to allow conversion)
            # 3. If it's a NetCDF file AND GRIB2 exists -> Hide it (Show GRIB2 instead)
            
            is_grib = filename.endswith('.grib2') or filename.endswith('.grb2')
            
            # Check corresponding GRIB name if this is a generic NetCDF
            corresponding_grib = os.path.splitext(filename)[0] + ".grib2"
            
            if not is_grib:
                # It's not a grib file. Check if we should show it.
                if corresponding_grib in grib_files:
                    continue # Hide, show the GRIB version instead
                    
            # ... parsing logic ...
            
            # Remove extension for parsing
            name_no_ext = os.path.splitext(filename)[0]
            
            # Parse WRF filename format: wrfout_d01_2025-09-18_00:00:00.grib2
            # Parts (after removing ext): ['wrfout', 'd01', '2025-09-18', '00:00:00']
            parts = name_no_ext.split('_')
            domain = parts[1] if len(parts) > 1 else 'unknown'
            
            # Reconstruct date string
            if len(parts) > 2:
                date_str = '_'.join(parts[2:])
            else:
                date_str = 'unknown'
            
            # Get file stats
            stat = os.stat(filepath)
            size_mb = stat.st_size / (1024 * 1024)
            
            files.append({
                'filename': filename,
                'path': filepath,
                'domain': domain,
                'date': date_str,
                'size_mb': round(size_mb, 2),
                'is_current': filepath == get_current_netcdf_path()
            })
        
        return jsonify({
            'files': files,
            'current': get_current_netcdf_path(),
            'data_dir': data_dir
        })
        
    except Exception as e:
        app.logger.error(f"Error listing NetCDF files: {e}", exc_info=True)
        return jsonify(error=f"Error listing NetCDF files: {e}"), 500


@app.route('/netcdf_files/select', methods=['POST'])
def select_netcdf_file():
    """
    Select a NetCDF file to use for data visualization.
    Expects JSON body: { "path": "data/wrfout_d01_2025-09-18_00:00:00" }
    """
    try:
        data = request.get_json()
        if not data or 'path' not in data:
            return jsonify(error="Missing 'path' in request body"), 400
        
        filepath = data['path']
        
        # Security check: ensure path is within data directory
        abs_data_dir = os.path.abspath(NETCDF_DATA_DIR)
        abs_filepath = os.path.abspath(filepath)
        if not abs_filepath.startswith(abs_data_dir):
            return jsonify(error="Invalid file path"), 400
        
        if not os.path.exists(filepath):
            return jsonify(error=f"File not found: {filepath}"), 404
            
        # Check if it is a NetCDF file, and if so, trigger or verify GRIB2 conversion
        active_filepath = filepath
        if not filepath.endswith('.grib2') and not filepath.endswith('.grb2'):
            grib_path = os.path.splitext(filepath)[0] + ".grib2"
            
            # Check if GRIB2 already exists and is fresher than NetCDF
            should_convert = True
            if os.path.exists(grib_path):
                nc_mtime = os.path.getmtime(filepath)
                grib_mtime = os.path.getmtime(grib_path)
                if grib_mtime > nc_mtime:
                    should_convert = False
                    app.logger.info(f"Using existing valid GRIB2 file: {grib_path}")
            
            if should_convert:
                app.logger.info(f"Triggering auto-conversion for {filepath} -> {grib_path}")
                converted_path = convert_to_grib2(filepath, grib_path)
                if not converted_path:
                     return jsonify(error="Automatic GRIB2 conversion failed. Check server logs."), 500
            
            active_filepath = grib_path

        # Try to open the file to verify it's a valid NetCDF or GRIB
        try:
            if active_filepath.endswith('.grib2') or active_filepath.endswith('.grb2'):
                 test_ds = xr.open_dataset(active_filepath, engine="cfgrib", backend_kwargs={'indexpath': ''})
            else:
                 test_ds = xr.open_dataset(active_filepath, engine="netcdf4")
            num_times = _get_num_times(test_ds)
            variables = list(test_ds.data_vars.keys())
            test_ds.close()
        except Exception as e:
            return jsonify(error=f"Invalid file: {e}"), 400
        
        # Switch to the new file
        set_current_netcdf_path(active_filepath)
        
        return jsonify({
            'success': True,
            'current': active_filepath,
            'original': filepath,
            'num_times': num_times,
            'variables': variables[:20]  # Limit to first 20 variables
        })
        
    except Exception as e:
        app.logger.error(f"Error selecting NetCDF file: {e}", exc_info=True)
        return jsonify(error=f"Error selecting NetCDF file: {e}"), 500


@app.route('/variables')
def get_variables():
    """Return list of available variables with metadata"""
    try:
        variables = []
        for var_id, config in VARIABLE_CONFIG.items():
            variables.append({
                'id': var_id,
                'name': config['name'],
                'description': config['description'],
                'units': config['units'],
                'colormap': config.get('colormap', 'viridis')
            })
        return jsonify(variables)
    except Exception as e:
        app.logger.error(f"Error getting variables: {e}")
        return jsonify(error=f"Error getting variables: {e}"), 500


@app.route('/variable_stats')
def get_variable_stats():
    """Return bounds and value range for a variable/time."""
    try:
        path = get_current_netcdf_path()
        if not path.endswith('.grib2') and not path.endswith('.grb2'):
             return jsonify(error="Visualization is ONLY supported for GRIB2 files."), 400

        time_index = request.args.get('time', default=0, type=int)
        variable_id = request.args.get('variable', default='PSFC', type=str)

        if variable_id not in VARIABLE_CONFIG:
            return jsonify(error=f"Invalid variable: {variable_id}"), 400

        ds = get_dataset()
        num_times = _get_num_times(ds)
        if time_index < 0 or time_index >= num_times:
            return jsonify(error=f"Invalid time index. Must be 0-{num_times-1}"), 404

        var_config = VARIABLE_CONFIG[variable_id]
        values = _get_variable_data(ds, variable_id, time_index)
        values = _apply_scale_offset(values, var_config)

        lons, lats = _get_coords(ds, time_index)

        vmin = float(np.nanmin(values))
        vmax = float(np.nanmax(values))
        min_lon = float(np.nanmin(lons))
        max_lon = float(np.nanmax(lons))
        min_lat = float(np.nanmin(lats))
        max_lat = float(np.nanmax(lats))

        return jsonify({
            "valueRange": [vmin, vmax],
            "bounds": [min_lon, min_lat, max_lon, max_lat],
            "colormap": var_config.get('colormap', 'viridis'),
            "units": var_config.get('units', ''),
            "name": var_config.get('description', variable_id)
        })
    except Exception as e:
        app.logger.error(f"Error getting variable stats: {e}", exc_info=True)
        return jsonify(error=f"Error getting variable stats: {e}"), 500


@app.route('/grid_sample')
def get_grid_sample():
    """Return a downsampled set of grid points for alignment checking."""
    try:
        stride = request.args.get('stride', default=50, type=int)
        if stride < 1:
            stride = 1

        ds = get_dataset()
        lons, lats = _get_coords(ds, 0)

        lons_s = lons[::stride, ::stride]
        lats_s = lats[::stride, ::stride]

        points = [
            {"lon": float(lon), "lat": float(lat)}
            for lon, lat in zip(lons_s.ravel(), lats_s.ravel())
            if np.isfinite(lon) and np.isfinite(lat)
        ]

        corners = [
            [float(lons[-1, 0]), float(lats[-1, 0])],   # TL
            [float(lons[-1, -1]), float(lats[-1, -1])], # TR
            [float(lons[0, -1]), float(lats[0, -1])],   # BR
            [float(lons[0, 0]), float(lats[0, 0])]      # BL
        ]

        return jsonify({
            "points": points,
            "corners": corners
        })
    except Exception as e:
        app.logger.error(f"Error getting grid sample: {e}", exc_info=True)
        return jsonify(error=f"Error getting grid sample: {e}"), 500


def _transparent_tile():
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


@app.route('/tiles/<int:z>/<int:x>/<int:y>')
def get_variable_tile(z, x, y):
    """Return WebMercator PNG tile for a variable/time using grid interpolation."""
    from scipy.interpolate import griddata
    
    try:
        path = get_current_netcdf_path()
        if not path.endswith('.grib2') and not path.endswith('.grb2'):
             app.logger.error("Request for tile from non-GRIB2 file. Denied.")
             return make_response(send_file(_transparent_tile(), mimetype='image/png'))

        time_index = request.args.get('time', default=0, type=int)
        variable_id = request.args.get('variable', default='PSFC', type=str)
        vmin_param = request.args.get('vmin', default=None, type=float)
        vmax_param = request.args.get('vmax', default=None, type=float)

        if variable_id not in VARIABLE_CONFIG:
            return jsonify(error=f"Invalid variable: {variable_id}"), 400

        ds = get_dataset()
        num_times = _get_num_times(ds)
        if time_index < 0 or time_index >= num_times:
            return jsonify(error=f"Invalid time index. Must be 0-{num_times-1}"), 404

        var_config = VARIABLE_CONFIG[variable_id]
        
        minx, miny, maxx, maxy = _tile_bounds_webmercator(z, x, y)
        
        # --- SMART SLICING START ---
        # Convert WebMercator bounds to Lat/Lon for slicing
        # Add padding to ensure coverage
        pad_meters = (maxx - minx) * 0.5 
        
        sl_min_lon, sl_min_lat = _webmercator_to_lonlat(minx - pad_meters, miny - pad_meters)
        sl_max_lon, sl_max_lat = _webmercator_to_lonlat(maxx + pad_meters, maxy + pad_meters)
        
        # Get slices
        lat_slice, lon_slice = _get_grid_slice(ds, sl_min_lon, sl_max_lon, sl_min_lat, sl_max_lat)
        
        # Slice the dataset
        # Note: GRIB2 dims are usually (step, latitude, longitude)
        # We need to apply slices to the already-selected (time) variable or ds
        
        # Get variable data (which might pull full array if we use _get_variable_data directly)
        # Optimization: Slice DS first, then get variable
        
        # We need to map variable name first
        target_var = None
        if variable_id in ds:
             target_var = variable_id
        else:
             # Check mapping
             for candidate in grib_map.get(variable_id, []):
                 if candidate in ds:
                     target_var = candidate
                     break
        
        if not target_var:
             return jsonify(error=f"Variable {variable_id} not found"), 404

        # Slice data
        try:
            # Assumes dims are (..., latitude, longitude)
            # We use the slices we calculated
            if 'latitude' in ds.dims and 'longitude' in ds.dims:
                da_sliced = ds[target_var].isel(latitude=lat_slice, longitude=lon_slice)
                
                # Also handle time
                da_sliced = _get_time_slice(ds, target_var, time_index).isel(latitude=lat_slice, longitude=lon_slice)
                
                # Get Coords
                sub_lats = ds['latitude'].isel(latitude=lat_slice).values
                sub_lons = ds['longitude'].isel(longitude=lon_slice).values
                
                # Meshgrid 1D -> 2D
                sub_lons_2d, sub_lats_2d = np.meshgrid(sub_lons, sub_lats)
            else:
                 # Fallback for non-compliant structure (shouldn't happen with strict GRIB2)
                 raise ValueError("Grid not regular regular_ll")

            values_subset = da_sliced.values
            
            # Apply scale/offset
            values_subset = _apply_scale_offset(values_subset, var_config)

        except Exception as slice_err:
             app.logger.warning(f"Slicing failed, falling back to full grid: {slice_err}")
             # Fallback to full read
             values = _get_variable_data(ds, variable_id, time_index)
             values_subset = _apply_scale_offset(values, var_config)
             lons_full, lats_full = _get_coords(ds, time_index)
             sub_lons_2d = lons_full
             sub_lats_2d = lats_full
        
        # Flatten subset
        values_flat = values_subset.ravel()
        
        # Project subset coords to WebMercator
        x_sub, y_sub = _lonlat_to_webmercator(sub_lons_2d, sub_lats_2d)
        x_flat = x_sub.ravel()
        y_flat = y_sub.ravel()
        
        # --- RENDER ---
        
        # Mask NaNs
        mask = np.isfinite(values_flat)
        if not np.any(mask):
             return make_response(send_file(_transparent_tile(), mimetype='image/png'))

        src_x = x_flat[mask]
        src_y = y_flat[mask]
        src_v = values_flat[mask]
        
        if len(src_v) < 4:
             # Not enough points to interpolate
             return make_response(send_file(_transparent_tile(), mimetype='image/png'))

        # Create regular grid for the tile (256x256)
        tile_size = 256
        xi = np.linspace(minx, maxx, tile_size)
        yi = np.linspace(miny, maxy, tile_size)
        xi_grid, yi_grid = np.meshgrid(xi, yi)

        # Interpolate
        zi = griddata(
            points=(src_x, src_y),
            values=src_v,
            xi=(xi_grid, yi_grid),
            method='linear',
            fill_value=np.nan
        )

        # Check if we have valid interpolated data
        if np.isnan(zi).all():
            response = make_response(send_file(_transparent_tile(), mimetype='image/png'))
            response.headers['Cache-Control'] = 'public, max-age=60'
            response.headers['X-Tile-Point-Count'] = str(int(np.count_nonzero(mask)))
            response.headers['X-Tile-Value-Range'] = 'nan,nan'
            response.headers['X-Tile-Bounds'] = f"{minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}"
            return response

        # Get value range for color normalization
        vmin = float(np.nanmin(zi))
        vmax = float(np.nanmax(zi))
        if vmin_param is not None and vmax_param is not None and vmin_param < vmax_param:
            vmin = vmin_param
            vmax = vmax_param

        # Normalize values to 0-1 range
        if vmax > vmin:
            normalized = (zi - vmin) / (vmax - vmin)
        else:
            normalized = np.zeros_like(zi)
        normalized = np.clip(normalized, 0, 1)

        # Apply colormap
        try:
            cmap = matplotlib.cm.get_cmap(var_config.get('colormap', 'viridis'))
        except:
            cmap = matplotlib.cm.get_cmap('viridis')
        
        # Create RGBA image
        rgba = cmap(normalized)
        # Set alpha to 0 for NaN values (transparent)
        rgba[..., 3] = np.where(np.isnan(zi), 0, 0.85)
        
        # Convert to 8-bit RGBA
        rgba_uint8 = (rgba * 255).astype(np.uint8)
        
        # Flip vertically because image origin is top-left, but our grid is bottom-left
        rgba_uint8 = np.flipud(rgba_uint8)
        
        pil_img = Image.fromarray(rgba_uint8, mode='RGBA')
        
        buf = io.BytesIO()
        pil_img.save(buf, format='PNG')
        buf.seek(0)

        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['Cache-Control'] = 'public, max-age=60'
        response.headers['X-Tile-Point-Count'] = str(int(np.count_nonzero(mask)))
        response.headers['X-Tile-Value-Range'] = f"{vmin:.4f},{vmax:.4f}"
        response.headers['X-Tile-Bounds'] = f"{minx:.2f},{miny:.2f},{maxx:.2f},{maxy:.2f}"
        return response
    except Exception as e:
        app.logger.error(f"Error generating tile: {e}", exc_info=True)
        response = make_response(send_file(_transparent_tile(), mimetype='image/png'))
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Tile-Error'] = str(e)
        response.headers['X-Tile-Point-Count'] = '0'
        response.headers['X-Tile-Value-Range'] = 'nan,nan'
        return response

@app.route('/slp_data')
def get_slp_data():
    session = Session()
    try:
        time_index = request.args.get('time', default=0, type=int)

        # Get the time_id for the given time_index
        # Assuming time_index directly corresponds to TimePoint.id (1-based)
        time_id_to_query = time_index + 1 # Assuming time_index directly corresponds to TimePoint.id
        time_point = session.query(TimePoint).filter(TimePoint.id == time_id_to_query).first()
        if not time_point:
            app.logger.debug(f"Invalid time index: {time_index}. time_id_to_query: {time_id_to_query}")
            return jsonify(error="Invalid time index."), 404
        
        # Fetch SLP data for the selected time_id
        slp_records = session.query(SlpData, SpatialGrid.longitude, SpatialGrid.latitude)            .join(SpatialGrid, SlpData.grid_id == SpatialGrid.id)            .filter(SlpData.time_id == time_point.id)            .order_by(SpatialGrid.id).all()

        if not slp_records:
            app.logger.debug(f"No SLP data found for time_id: {time_id_to_query}")
            return jsonify(error="No SLP data found for this time index."), 404

        # Prepare data for datashader
        lons = []
        lats = []
        values = []
        min_val = float('inf')
        max_val = float('-inf')
        min_lon = float('inf')
        max_lon = float('-inf')
        min_lat = float('inf')
        max_lat = float('-inf')

        for record, lon, lat in slp_records:
            value = float(record.pressure_value)
            lons.append(float(lon))
            lats.append(float(lat))
            values.append(value)
            min_val = min(min_val, value)
            max_val = max(max_val, value)
            min_lon = min(min_lon, float(lon))
            max_lon = max(max_lon, float(lon))
            min_lat = min(min_lat, float(lat))
            max_lat = max(max_lat, float(lat))
            app.logger.debug(f"Record: time_id={record.time_id}, grid_id={record.grid_id}, lon={lon}, lat={lat}, value={value}")

        app.logger.info(f"Min/Max of pressure data: {min_val} / {max_val}")
        app.logger.debug(f"Lengths: lons={len(lons)}, lats={len(lats)}, values={len(values)}")
        app.logger.debug(f"First 5 lons: {lons[:5]}")
        app.logger.debug(f"First 5 lats: {lats[:5]}")
        app.logger.debug(f"First 5 values: {values[:5]}")

        # Reconstruct the 2D grid
        grid_height = 60
        grid_width = 73

        try:
            lon_grid = np.array(lons).reshape(grid_height, grid_width)
            lat_grid = np.array(lats).reshape(grid_height, grid_width)
            value_grid = np.array(values).reshape(grid_height, grid_width)
            app.logger.debug(f"Reshaped shapes: lon_grid={lon_grid.shape}, lat_grid={lat_grid.shape}, value_grid={value_grid.shape}")
            app.logger.debug(f"lon_grid[0, :5]: {lon_grid[0, :5]}")
            app.logger.debug(f"lat_grid[0, :5]: {lat_grid[0, :5]}")
            app.logger.debug(f"value_grid[0, :5]: {value_grid[0, :5]}")
        except ValueError as e:
            app.logger.error(f"Error reshaping data: {e}. Expected shape {grid_height}x{grid_width}, got {len(lons)} elements.")
            return jsonify(error="Data reshaping failed. Check grid dimensions."), 500

        # Use matplotlib's pcolormesh to create a proper mesh from the curvilinear grid
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        
        # Create a figure with the desired output size
        dpi = 100
        fig = Figure(figsize=(800/dpi, 600/dpi), dpi=dpi)
        fig.patch.set_alpha(0.0)  # Make figure background transparent
        ax = fig.add_subplot(111)
        ax.patch.set_alpha(0.0)  # Make axes background transparent
        
        # Create the mesh plot with the 2D coordinate arrays
        mesh = ax.pcolormesh(lon_grid, lat_grid, value_grid, 
                             cmap=matplotlib.cm.viridis, 
                             shading='auto',
                             rasterized=True,
                             alpha=0.85)  # Semi-transparent overlay
        
        # Set the axis limits to match the data bounds
        ax.set_xlim(min_lon, max_lon)
        ax.set_ylim(min_lat, max_lat)
        ax.set_aspect('auto')
        
        # Remove axes and margins for clean overlay
        ax.axis('off')
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
        
        # Get the bounds of the data
        bounds = [min_lon, min_lat, max_lon, max_lat]
        app.logger.info(f"Generated image bounds: {bounds}")

        # Render to PNG
        canvas = FigureCanvasAgg(fig)
        img_byte_arr = io.BytesIO()
        canvas.print_png(img_byte_arr)
        app.logger.info(f"Image saved as PNG. Bytes in buffer: {img_byte_arr.tell()}")
        img_byte_arr.seek(0)
        app.logger.info(f"Generated image size (bytes): {len(img_byte_arr.getvalue())}")

        # Create response and add custom headers
        response = make_response(send_file(img_byte_arr, mimetype='image/png'))
        response.headers['X-Image-Bounds'] = ",".join(map(str, bounds))
        response.headers['Access-Control-Expose-Headers'] = 'X-Image-Bounds'

        return response

    except Exception as e:
        app.logger.error(f"An error occurred during data processing: {e}")
        return jsonify(error=f"An error occurred during data processing: {e}"), 500
    finally:
        session.close()

@app.route('/variable_data')
def get_variable_data():
    """Get variable data directly from NetCDF file"""
    try:
        time_index = request.args.get('time', default=0, type=int)
        variable_id = request.args.get('variable', default='PSFC', type=str)
        path = get_current_netcdf_path()
        
        # Validate variable
        if variable_id not in VARIABLE_CONFIG:
            return jsonify(error=f"Invalid variable: {variable_id}"), 400
        
        var_config = VARIABLE_CONFIG[variable_id]

        ds = get_dataset()
        num_times = _get_num_times(ds)
        if time_index < 0 or time_index >= num_times:
            return jsonify(error=f"Invalid time index. Must be 0-{num_times-1}"), 404

        # Use cache
        try:
            png_bytes, meta = _get_cached_variable_image(
                path, 
                time_index, 
                variable_id, 
                var_config.get('colormap', 'viridis'),
                var_config.get('scale', 1.0),
                var_config.get('offset', 0.0),
                var_config.get('units', ''),
                var_config.get('description', '')
            )
        except ValueError as ve:
             return jsonify(error=str(ve)), 400
        except KeyError as ke:
             return jsonify(error=str(ke)), 404
             
        buf = io.BytesIO(png_bytes)
        bounds = meta['bounds']
        corners = meta['corners']
        vmin = meta['vmin']
        vmax = meta['vmax']
        
        # Create response with metadata
        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['X-Image-Bounds'] = ",".join(map(str, bounds))
        
        corners_str = ";".join([f"{c[0]},{c[1]}" for c in corners])
        response.headers['X-Image-Corners'] = corners_str
        response.headers['X-Variable-Name'] = var_config['description']
        response.headers['X-Variable-Units'] = var_config['units']
        response.headers['X-Value-Min'] = str(round(vmin, 2))
        response.headers['X-Value-Max'] = str(round(vmax, 2))
        response.headers['X-Colormap'] = var_config.get('colormap', 'viridis')
        response.headers['Access-Control-Expose-Headers'] = 'X-Image-Bounds,X-Image-Corners,X-Variable-Name,X-Variable-Units,X-Value-Min,X-Value-Max,X-Colormap'
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error processing variable data: {e}", exc_info=True)
        return jsonify(error=f"Error processing variable data: {e}"), 500

@app.route('/variable_data_raw')
def get_variable_data_raw():
    """Get raw variable data as JSON for client-side rendering (deck.gl)"""
    try:
        path = get_current_netcdf_path()
        if not path.endswith('.grib2') and not path.endswith('.grb2'):
             return jsonify(error="Visualization is ONLY supported for GRIB2 files."), 400

        time_index = request.args.get('time', default=0, type=int)
        variable_id = request.args.get('variable', default='PSFC', type=str)
        stride = request.args.get('stride', default=1, type=int)
        if stride < 1:
            stride = 1
        
        # Validate variable
        if variable_id not in VARIABLE_CONFIG:
            return jsonify(error=f"Invalid variable: {variable_id}"), 400
        
        var_config = VARIABLE_CONFIG[variable_id]
        
        # Open NetCDF file
        ds = get_dataset()
        
        # Check if time index is valid
        num_times = _get_num_times(ds)
        if time_index < 0 or time_index >= num_times:
            return jsonify(error=f"Invalid time index. Must be 0-{num_times-1}"), 404
        
        # Get the variable data
        # Get the variable data
        if variable_id == 'WSPD':
            u_name = _map_variable(ds, 'U10')
            v_name = _map_variable(ds, 'V10')
            if not u_name or not v_name:
                return jsonify(error="Wind variables U10/V10 not found"), 404
            u = _get_time_slice(ds, u_name, time_index)
            v = _get_time_slice(ds, v_name, time_index)
            var_data = np.sqrt(u**2 + v**2)
            # Mask invalid/outlier values
            var_data = var_data.where(var_data < 500)
        elif variable_id not in ds:
            return jsonify(error=f"Variable {variable_id} not found in NetCDF file"), 404
        else:
            var_data = ds[variable_id].isel(Time=time_index)
        
        # Handle 3D variables - take surface level
        if 'bottom_top' in var_data.dims:
            var_data = var_data.isel(bottom_top=0)
        
        # Get coordinate arrays
        lons, lats = _get_coords(ds, time_index)
        values = var_data.values

        if stride > 1:
            lons = lons[::stride, ::stride]
            lats = lats[::stride, ::stride]
            values = values[::stride, ::stride]
        
        # Apply unit conversion if needed
        if 'scale' in var_config:
            values = values * var_config['scale']
        if 'offset' in var_config:
            values = values + var_config['offset']
        
        app.logger.info(
            f"Raw data for {variable_id}: shape={values.shape}, "
            f"range=[{np.nanmin(values):.2f}, {np.nanmax(values):.2f}]"
        )
        
        # Flatten to points array (vectorized)
        mask = ~np.isnan(values)
        flat_lons = lons[mask].ravel()
        flat_lats = lats[mask].ravel()
        flat_vals = values[mask].ravel()
        points = [
            {
                'lon': round(float(lon), 4),
                'lat': round(float(lat), 4),
                'value': round(float(val), 2)
            }
            for lon, lat, val in zip(flat_lons, flat_lats, flat_vals)
        ]
        
        # Get bounds and value range
        result = {
            'points': points,
            'bounds': [
                round(float(np.nanmin(lons)), 4),
                round(float(np.nanmin(lats)), 4),
                round(float(np.nanmax(lons)), 4),
                round(float(np.nanmax(lats)), 4)
            ],
            'variable': variable_id,
            'name': var_config['name'],
            'description': var_config['description'],
            'units': var_config['units'],
            'valueRange': [
                round(float(np.nanmin(values)), 2),
                round(float(np.nanmax(values)), 2)
            ],
            'colormap': var_config['colormap'],
            'count': len(points),
            'stride': stride
        }
        
        app.logger.info(f"Returning {len(points)} points for {variable_id}")
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error processing raw variable data: {e}", exc_info=True)
        return jsonify(error=f"Error processing raw variable data: {e}"), 500

@app.route('/wind_data')
def get_wind_data():
    """Get U and V components for wind particle animation"""
    try:
        path = get_current_netcdf_path()
        if not path.endswith('.grib2') and not path.endswith('.grb2'):
             return jsonify(error="Visualization is ONLY supported for GRIB2 files."), 400

        time_index = request.args.get('time', default=0, type=int)
        stride = request.args.get('stride', default=1, type=int)
        if stride < 1:
            stride = 1
        
        # Open NetCDF file
        ds = get_dataset()
        
        # Check time index
        num_times = _get_num_times(ds)
        if time_index < 0 or time_index >= num_times:
            return jsonify(error=f"Invalid time index. Must be 0-{num_times-1}"), 404
            
        # Get U10 and V10
        if 'U10' not in ds and 'u' not in ds and '10u' not in ds:
             # Try mapping check
             u_name = _map_variable(ds, 'U10')
             v_name = _map_variable(ds, 'V10')
             if not u_name or not v_name:
                return jsonify(error="Wind variables U10/V10 not found"), 404
        else:
             u_name = _map_variable(ds, 'U10')
             v_name = _map_variable(ds, 'V10')
            
        u_data = _get_time_slice(ds, u_name, time_index).values
        v_data = _get_time_slice(ds, v_name, time_index).values
        
        lons, lats = _get_coords(ds, time_index)

        if stride > 1:
            u_data = u_data[::stride, ::stride]
            v_data = v_data[::stride, ::stride]
            lons = lons[::stride, ::stride]
            lats = lats[::stride, ::stride]
        
        app.logger.info(f"Wind data shape: {u_data.shape}")
        
        # Flatten to points array (vectorized)
        mask = ~(np.isnan(u_data) | np.isnan(v_data))
        flat_lons = lons[mask].ravel()
        flat_lats = lats[mask].ravel()
        flat_u = u_data[mask].ravel()
        flat_v = v_data[mask].ravel()
        points = [
            {
                'lon': round(float(lon), 4),
                'lat': round(float(lat), 4),
                'u': round(float(u), 2),
                'v': round(float(v), 2)
            }
            for lon, lat, u, v in zip(flat_lons, flat_lats, flat_u, flat_v)
        ]
                    
        return jsonify({
            'points': points,
            'bounds': [
                round(float(np.nanmin(lons)), 4),
                round(float(np.nanmin(lats)), 4),
                round(float(np.nanmax(lons)), 4),
                round(float(np.nanmax(lats)), 4)
            ],
            'count': len(points),
            'stride': stride
        })
        
    except Exception as e:
        app.logger.error(f"Error processing wind data: {e}", exc_info=True)
        return jsonify(error=f"Error processing wind data: {e}"), 500



@lru_cache(maxsize=32)
def _get_cached_variable_image(path, time_index, variable_id, colormap, scale, offset, units, description):
    """Cached generation of variable visualization."""
    if not path.endswith('.grib2') and not path.endswith('.grb2'):
        raise ValueError("Not a GRIB2 file")
        
    ds = get_dataset()
    
    # Use helper to get data (handles mapping)
    try:
        values = _get_variable_data(ds, variable_id, time_index)
    except KeyError:
        raise KeyError(f"Variable {variable_id} not found")
        
    lons, lats = _get_coords(ds, time_index)
    
    # Calculate bounds
    min_lon = float(np.nanmin(lons))
    max_lon = float(np.nanmax(lons))
    min_lat = float(np.nanmin(lats))
    max_lat = float(np.nanmax(lats))
    
    # Check shape mismatch (rare but possible if coords are 1D and values 2D)
    if values.shape != lons.shape:
        # If coords are meshgrid-able?
        pass 
        
    # Validations
    values = values.astype(float)
    
    # Scale/Offset
    if scale is not None: values = values * scale
    if offset is not None: values = values + offset
            
    vmin = float(np.nanmin(values))
    vmax = float(np.nanmax(values))
    
    # Rendering
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import matplotlib.cm
    
    try:
        cmap = matplotlib.cm.get_cmap(colormap).copy()
    except:
        cmap = matplotlib.cm.viridis.copy()
    cmap.set_bad(alpha=0)
    
    masked_values = np.ma.masked_invalid(values)
    
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat
    if lat_range == 0: lat_range = 1
    geo_aspect = lon_range / lat_range
    
    img_height = 800 # Reduced from 1200 for perf, still good quality
    img_width = int(img_height * geo_aspect)
    img_width = max(img_width, 800)
    dpi = 96
    
    fig = Figure(figsize=(img_width/dpi, img_height/dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.patch.set_alpha(0.0)
    
    # pcolormesh is slow. pcolorfast? or imshow if regular?
    # Our grid is curvilinear, so pcolormesh is correct correctness-wise.
    # To speed up, we can use rasterized=True (default for Agg?)
    # shading='gouraud' is smoother but slower? 'auto' or 'nearest' is faster?
    # Wind layer needs smooth? 'flat' is fastest. 'gouraud' looks better.
    # We stick with gouraud but rely on caching.
    
    ax.pcolormesh(lons, lats, masked_values, cmap=cmap, shading='gouraud', alpha=0.85, vmin=vmin, vmax=vmax)
    
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.axis('off')
    
    canvas = FigureCanvasAgg(fig)
    buf = io.BytesIO()
    canvas.print_png(buf)
    buf.seek(0)
    
    corners = [
        [float(lons[-1, 0]), float(lats[-1, 0])],
        [float(lons[-1, -1]), float(lats[-1, -1])],
        [float(lons[0, -1]), float(lats[0, -1])],
        [float(lons[0, 0]), float(lats[0, 0])]
    ]
    
    meta = {
        'bounds': [min_lon, min_lat, max_lon, max_lat],
        'corners': corners,
        'vmin': vmin,
        'vmax': vmax
    }
    
    return buf.getvalue(), meta


@lru_cache(maxsize=32)
def _get_cached_wind_texture(path, time_index):
    """Cached generation of wind texture."""
    if not path.endswith('.grib2') and not path.endswith('.grb2'):
        raise ValueError("Not a GRIB2 file")
    
    # We re-fetch dataset here. Since get_dataset is efficient, this is fine.
    # Note: get_dataset() uses global cache, so we must be careful if file changes.
    # But path is part of cache key, so if path changes, cache key changes.
    # If content of SAME path changes, lru_cache won't know unless we clear it.
    # For now assuming file path is unique per version or restarted.
    
    ds = get_dataset()
    u_name = _map_variable(ds, 'U10')
    v_name = _map_variable(ds, 'V10')
    if not u_name or not v_name:
         raise KeyError("Wind variables not found")
    
    u_data = _get_time_slice(ds, u_name, time_index).values
    v_data = _get_time_slice(ds, v_name, time_index).values
    lons, lats = _get_coords(ds, time_index)
    
    buf, metadata = encode_wind_to_png(u_data, v_data)
    
    # Cache numpy results? No, just bytes.
    return buf.getvalue(), metadata, lons, lats

@app.route('/wind_texture')
def get_wind_texture():
    """
    Return wind data as a PNG texture for WebGL rendering.
    
    R channel = U wind component (normalized 0-255)
    G channel = V wind component (normalized 0-255)
    
    Response headers include metadata for decoding:
    - X-Wind-U-Range: "min,max" (m/s)
    - X-Wind-V-Range: "min,max" (m/s)
    - X-Wind-Bounds: "minLon,minLat,maxLon,maxLat"
    - X-Wind-Grid-Size: "width,height"
    """
    try:
        path = get_current_netcdf_path()
        time_index = request.args.get('time', default=0, type=int)
        
        # Use cached function
        # Returns bytes, metadata dict, and coordinate arrays (numpy)
        # Note: lons/lats are needed for bounds/corners. numpy arrays are returned from cache?
        # Yes, lru_cache stores return values.
        
        try:
             png_bytes, metadata, lons, lats = _get_cached_wind_texture(path, time_index)
        except ValueError as ve:
             return jsonify(error=str(ve)), 400
        except KeyError as ke:
             return jsonify(error=str(ke)), 404
             
        buf = io.BytesIO(png_bytes)
        
        # Get bounds
        min_lon = float(np.nanmin(lons))
        max_lon = float(np.nanmax(lons))
        min_lat = float(np.nanmin(lats))
        max_lat = float(np.nanmax(lats))
        
        # Check if metadata JSON is requested
        if request.args.get('metadata') == 'true':
            return jsonify({
                'uMin': metadata['u_min'],
                'uMax': metadata['u_max'],
                'vMin': metadata['v_min'],
                'vMax': metadata['v_max'],
                'width': metadata['width'],
                'height': metadata['height'],
                'bounds': [min_lon, min_lat, max_lon, max_lat]
            })
        
        # Standard orientation (Data[0] is South -> t=0 Bottom)
        # No flip needed
        
        # Get corners (TL, TR, BR, BL) for curvilinear alignment
        corners = [
            [float(lons[-1, 0]), float(lats[-1, 0])],   # Top-left (NW)
            [float(lons[-1, -1]), float(lats[-1, -1])], # Top-right (NE)
            [float(lons[0, -1]), float(lats[0, -1])],   # Bottom-right (SE)
            [float(lons[0, 0]), float(lats[0, 0])]      # Bottom-left (SW)
        ]
        corners_str = ";".join([f"{c[0]},{c[1]}" for c in corners])
        
        app.logger.info(
            f"Wind texture: {metadata['width']}x{metadata['height']}, "
            f"U=[{metadata['u_min']:.2f}, {metadata['u_max']:.2f}], "
            f"V=[{metadata['v_min']:.2f}, {metadata['v_max']:.2f}]"
        )
        
        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['X-Wind-U-Range'] = f"{metadata['u_min']:.4f},{metadata['u_max']:.4f}"
        response.headers['X-Wind-V-Range'] = f"{metadata['v_min']:.4f},{metadata['v_max']:.4f}"
        response.headers['X-Wind-Bounds'] = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"
        response.headers['X-Wind-Corners'] = corners_str
        response.headers['X-Wind-Grid-Size'] = f"{metadata['width']},{metadata['height']}"
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.headers['Access-Control-Expose-Headers'] = (
            'X-Wind-U-Range,X-Wind-V-Range,X-Wind-Bounds,X-Wind-Corners,X-Wind-Grid-Size'
        )
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error generating wind texture: {e}", exc_info=True)
        return jsonify(error=f"Error generating wind texture: {e}"), 500


@lru_cache(maxsize=32)
def _get_cached_coords_texture(path, time_index):
    """Cached generation of coordinate texture."""
    if not path.endswith('.grib2') and not path.endswith('.grb2'):
        raise ValueError("Not a GRIB2 file")
        
    ds = get_dataset()
    lons, lats = _get_coords(ds, time_index)
    
    buf, metadata = create_coordinate_texture(lons, lats)
    return buf.getvalue(), metadata

@app.route('/coords_texture')
def get_coords_texture():
    """
    Return grid coordinates as a PNG texture for precise WebGL mapping.
    
    R/G channels = Longitude (16-bit)
    B/A channels = Latitude (16-bit)
    """
    try:
        path = get_current_netcdf_path()
        time_index = request.args.get('time', default=0, type=int)
        
        try:
             png_bytes, metadata = _get_cached_coords_texture(path, time_index)
        except ValueError as ve:
             return jsonify(error=str(ve)), 400
        
        buf = io.BytesIO(png_bytes)
        
        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['X-Coords-Lon-Range'] = f"{metadata['min_lon']:.6f},{metadata['max_lon']:.6f}"
        response.headers['X-Coords-Lat-Range'] = f"{metadata['min_lat']:.6f},{metadata['max_lat']:.6f}"
        response.headers['X-Coords-Grid-Size'] = f"{metadata['width']},{metadata['height']}"
        response.headers['Access-Control-Expose-Headers'] = 'X-Coords-Lon-Range,X-Coords-Lat-Range,X-Coords-Grid-Size'
        response.headers['Cache-Control'] = 'public, max-age=31536000' # Static grid, long cache
        
        return response
    except Exception as e:
        app.logger.error(f"Error serving coords texture: {e}", exc_info=True)
        return jsonify(error=str(e)), 500
        response.headers['X-Coords-Lat-Range'] = f"{metadata['min_lat']:.6f},{metadata['max_lat']:.6f}"
        response.headers['X-Coords-Grid-Size'] = f"{metadata['width']},{metadata['height']}"
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.headers['Access-Control-Expose-Headers'] = (
            'X-Coords-Lon-Range,X-Coords-Lat-Range,X-Coords-Grid-Size'
        )
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error generating coords texture: {e}", exc_info=True)
        return jsonify(error=f"Error generating coords texture: {e}"), 500


@app.route('/color_ramp')
def get_color_ramp():
    """Return a color ramp texture for wind speed visualization."""
    try:
        colormap = request.args.get('colormap', default='viridis', type=str)
        steps = request.args.get('steps', default=256, type=int)
        steps = max(16, min(512, steps))  # Clamp to reasonable range
        
        buf = create_color_ramp(colormap, steps)
        
        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 1 day
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error generating color ramp: {e}", exc_info=True)
        return jsonify(error=f"Error generating color ramp: {e}"), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)