"""
Maritime Platform - Metadata API (Wind Support Update)
"""
from __future__ import annotations
import logging
import os
import io
import hmac
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
import geojson
import mercantile
from scipy.spatial import cKDTree
from flask import Flask, Response, g, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
CORS(app, origins=cors_origins or "*")
app.logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

render_lock = threading.Lock()
metrics_lock = threading.Lock()
rate_limit_lock = threading.Lock()
REQUEST_METRICS = {
    "total": 0,
    "latency_seconds_sum": 0.0,
    "status_classes": {},
    "endpoints": {},
    "rate_limited": 0,
}
PUBLIC_ENDPOINTS = {"/health", "/ready", "/version"}
RATE_LIMIT_BUCKETS: defaultdict[str, deque[float]] = defaultdict(deque)

DATA_DIR = os.getenv("NETCDF_DATA_DIR", "data")
DEFAULT_NETCDF = os.getenv("NETCDF_PATH", "data/wrfout_d01_2026-09-02_00:00:00")
COG_ROOT = os.getenv("COG_ROOT", "/cog")
BUILD_VERSION = os.getenv("BUILD_VERSION", "dev")
BUILD_SHA = os.getenv("BUILD_SHA", "unknown")
BUILD_DATE = os.getenv("BUILD_DATE", "unknown")

_CURRENT_FILE: dict[str, str] = {"path": DEFAULT_NETCDF}

VARIABLE_CONFIG: dict[str, dict] = {
    "PSFC":     {"name": "表面氣壓", "units": "hPa", "colormap": "viridis", "scale": 0.01, "offset": 0.0, "category": "weather", "description": "近地面氣壓場，可搭配等壓線判讀天氣系統。", "candidates": ["PSFC", "sp", "P"]},
    "T2":       {"name": "2米溫度", "units": "°C", "colormap": "RdYlBu_r", "scale": 1.0, "offset": -273.15, "category": "weather", "description": "2 公尺氣溫，適合檢視冷暖區與日夜變化。", "candidates": ["T2", "T"]},
    "RAINC":    {"name": "對流降水", "units": "mm", "colormap": "YlGnBu", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "累積對流降水量。", "candidates": ["RAINC", "tp"]},
    "RAINNC":   {"name": "網格降水", "units": "mm", "colormap": "YlGnBu", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "累積非對流降水量。", "candidates": ["RAINNC"]},
    "U10":      {"name": "U風分量", "units": "m/s", "colormap": "RdBu_r", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "10 公尺東西向風速分量。", "candidates": ["U10", "U"]},
    "V10":      {"name": "V風分量", "units": "m/s", "colormap": "RdBu_r", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "10 公尺南北向風速分量。", "candidates": ["V10", "V"]},
    "REFD_MAX": {"name": "雷達反射率", "units": "dBZ", "colormap": "gist_ncar", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "最大雷達反射率，可用於強回波判讀。", "candidates": ["REFD_MAX", "refd"]},
    "WSPD":     {"name": "風速", "units": "m/s", "colormap": "plasma", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "由 U/V 風分量推導的水平風速。", "candidates": ["WSPD", "wspd"]},
    "T_LEV":    {"name": "高空溫度", "units": "°C", "colormap": "RdYlBu_r", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "模式垂直層上的氣溫。", "candidates": ["T_LEV", "T"]},
    "P_HYD":    {"name": "高空氣壓", "units": "hPa", "colormap": "viridis", "scale": 0.01, "offset": 0.0, "category": "weather", "description": "模式垂直層上的氣壓。", "candidates": ["P_HYD"]},
    "WSPD_LEV": {"name": "高空風速", "units": "m/s", "colormap": "plasma", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "模式垂直層上的水平風速。", "candidates": ["WSPD_LEV", "U"]},
    "REFL_10CM":{"name": "高空雷達反射率", "units": "dBZ", "colormap": "gist_ncar", "scale": 1.0, "offset": 0.0, "category": "weather", "description": "10 cm 雷達反射率。", "candidates": ["REFL_10CM"]},
    "SST":      {"name": "海溫", "units": "°C", "colormap": "turbo", "scale": 1.0, "offset": -273.15, "category": "marine", "description": "海表溫度；若資料已是攝氏，請在前處理階段保留單位 metadata。", "candidates": ["SST", "SSTK", "sea_surface_temperature", "sst"]},
    "WAVE_HS":  {"name": "有效波高", "units": "m", "colormap": "magma", "scale": 1.0, "offset": 0.0, "category": "marine", "description": "有效波高，用於航線風險與海況判讀。", "candidates": ["WAVE_HS", "HS", "HTSGW", "swh", "VHM0"]},
    "WAVE_TP":  {"name": "主波週期", "units": "s", "colormap": "viridis", "scale": 1.0, "offset": 0.0, "category": "marine", "description": "主波週期或尖峰週期。", "candidates": ["WAVE_TP", "TP", "PERPW", "pp1d"]},
    "WAVE_DIR": {"name": "波向", "units": "°", "colormap": "twilight", "scale": 1.0, "offset": 0.0, "category": "marine", "description": "主要波向。", "candidates": ["WAVE_DIR", "DIRPW", "VMDR", "mwd"]},
    "CURRENT_SPD": {"name": "海流速", "units": "m/s", "colormap": "plasma", "scale": 1.0, "offset": 0.0, "category": "marine", "description": "由海流 U/V 分量推導的流速。", "candidates": ["CURRENT_SPD", "CURR_SPD", "uo"]},
    "SSH":      {"name": "海面高度", "units": "m", "colormap": "RdBu_r", "scale": 1.0, "offset": 0.0, "category": "marine", "description": "海面高度或潮位異常。", "candidates": ["SSH", "zos", "tide", "TIDE"]},
}

_DS_CACHE: dict = {
    "path": None,
    "mtime": None,
    "ds": None,
    "xlong": None,
    "xlat": None,
    "coord_tree": None,
    "coord_shape": None,
    "coord_radius": None,
    "coord_source_indices": None,
}
_BLANK_TILE_BYTES = None

@app.before_request
def start_request_timer() -> None:
    g.request_started_at = time.perf_counter()

@app.before_request
def enforce_api_key():
    configured_key = os.getenv("API_KEY", "")
    if not configured_key or request.method == "OPTIONS" or request.path in PUBLIC_ENDPOINTS:
        return None

    supplied_key = request.headers.get("X-API-Key", "")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        supplied_key = auth_header.removeprefix("Bearer ").strip()

    if hmac.compare_digest(supplied_key, configured_key):
        return None

    return jsonify(error="Unauthorized"), 401

@app.before_request
def enforce_rate_limit():
    if request.method == "OPTIONS" or request.path in PUBLIC_ENDPOINTS:
        return None

    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "0") or "0")
    if limit <= 0:
        return None

    window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60") or "60")
    now = time.time()
    client_id = request.headers.get("X-API-Key") or request.headers.get("Authorization") or request.remote_addr or "anonymous"

    with rate_limit_lock:
        bucket = RATE_LIMIT_BUCKETS[client_id]
        while bucket and now - bucket[0] >= window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0]))) if bucket else window_seconds
            REQUEST_METRICS["rate_limited"] += 1
            response = jsonify(error="Rate limit exceeded")
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response
        bucket.append(now)

    return None

@app.after_request
def apply_operational_headers(response):
    elapsed = time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())
    endpoint = request.url_rule.rule if request.url_rule else request.path
    status_class = f"{response.status_code // 100}xx"

    with metrics_lock:
        REQUEST_METRICS["total"] += 1
        REQUEST_METRICS["latency_seconds_sum"] += elapsed
        REQUEST_METRICS["status_classes"][status_class] = REQUEST_METRICS["status_classes"].get(status_class, 0) + 1
        REQUEST_METRICS["endpoints"][endpoint] = REQUEST_METRICS["endpoints"].get(endpoint, 0) + 1

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-Response-Time-ms"] = f"{elapsed * 1000:.2f}"
    return response

def get_blank_tile() -> bytes:
    global _BLANK_TILE_BYTES
    if _BLANK_TILE_BYTES is None:
        buf = io.BytesIO()
        Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(buf, format="PNG")
        _BLANK_TILE_BYTES = buf.getvalue()
    return _BLANK_TILE_BYTES

def resolve_dataset_path() -> str | None:
    configured = Path(_CURRENT_FILE["path"])
    if configured.exists():
        return str(configured)

    data_dir = Path(DATA_DIR)
    if not data_dir.exists():
        return None

    candidates = sorted(
        f for f in data_dir.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and (f.name.startswith("wrfout") or f.suffix.lower() in (".nc", ".nc4", ".grib", ".grib2"))
    )
    if not candidates:
        return None

    fallback = str(candidates[0])
    app.logger.warning("Configured NETCDF_PATH not found: %s. Falling back to %s", configured, fallback)
    _CURRENT_FILE["path"] = fallback
    return fallback

def is_dataset_candidate(path: Path) -> bool:
    return (
        path.is_file()
        and not path.name.startswith(".")
        and (path.name.startswith("wrfout") or path.suffix.lower() in (".nc", ".nc4", ".grib", ".grib2"))
    )

def resolve_selectable_dataset(path_value: str) -> Path | None:
    data_dir = Path(DATA_DIR).resolve()
    requested = Path(path_value)
    if not requested.is_absolute():
        requested = Path.cwd() / requested

    try:
        resolved = requested.resolve()
        resolved.relative_to(data_dir)
    except (OSError, ValueError):
        return None

    if not is_dataset_candidate(resolved):
        return None
    return resolved

def _open_grib2_layer(path: str, type_of_level: str) -> xr.Dataset | None:
    try:
        return xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"typeOfLevel": type_of_level}, "indexpath": ""})
    except: return None

def get_dataset() -> xr.Dataset:
    path = resolve_dataset_path()
    if path is None:
        return xr.Dataset()
    try: mtime = os.path.getmtime(path)
    except: return xr.Dataset()

    if _DS_CACHE["ds"] is None or _DS_CACHE["path"] != path or _DS_CACHE["mtime"] != mtime:
        if _DS_CACHE["ds"] is not None:
            try: _DS_CACHE["ds"].close()
            except: pass
        try:
            ds = xr.open_dataset(path, engine="netcdf4")
            if "PSFC" not in ds and "P" in ds and "PB" in ds:
                ds["PSFC"] = (ds["P"] + ds["PB"]).isel(bottom_top=0)
            if "T2" not in ds and "T" in ds:
                ds["T2"] = ds["T"].isel(bottom_top=0) + 300.0
            app.logger.info(f"Loaded NetCDF: {path}")
        except Exception as e:
            app.logger.warning(f"Fallback to GRIB2: {e}")
            ds = xr.open_dataset(path)
        _DS_CACHE["ds"], _DS_CACHE["path"], _DS_CACHE["mtime"] = ds, path, mtime
        _DS_CACHE["xlong"], _DS_CACHE["xlat"] = None, None
        _DS_CACHE["coord_tree"], _DS_CACHE["coord_shape"], _DS_CACHE["coord_radius"] = None, None, None
        _DS_CACHE["coord_source_indices"] = None
    return _DS_CACHE["ds"]

def get_coordinates(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    path = _CURRENT_FILE["path"]
    if _DS_CACHE["path"] == path and _DS_CACHE["xlong"] is not None and _DS_CACHE["xlat"] is not None:
        return _DS_CACHE["xlong"], _DS_CACHE["xlat"]

    lons_da = ds.coords.get("XLONG", ds.coords.get("longitude"))
    if lons_da is None and "XLONG" in ds:
        lons_da = ds["XLONG"]
    lats_da = ds.coords.get("XLAT", ds.coords.get("latitude"))
    if lats_da is None and "XLAT" in ds:
        lats_da = ds["XLAT"]

    if lons_da is None or lats_da is None:
        raise ValueError("Coordinate variables XLONG/longitude and XLAT/latitude not found in dataset")

    ln, lt = lons_da.values, lats_da.values
    if ln.ndim == 3:
        ln, lt = ln[0], lt[0]

    _DS_CACHE["xlong"] = ln
    _DS_CACHE["xlat"] = lt
    return ln, lt

def normalize_longitudes(lons: np.ndarray) -> np.ndarray:
    return (np.asarray(lons, dtype="float64") + 180.0) % 360.0 - 180.0

def continuous_longitudes(lons: np.ndarray) -> np.ndarray:
    lon_values = np.asarray(lons, dtype="float64")
    finite = lon_values[np.isfinite(lon_values)]
    if finite.size == 0:
        return lon_values

    normalized = normalize_longitudes(lon_values)
    positive = lon_values % 360.0
    finite_normalized = normalized[np.isfinite(normalized)]
    finite_positive = positive[np.isfinite(positive)]
    norm_span = float(np.nanmax(finite_normalized) - np.nanmin(finite_normalized))
    positive_span = float(np.nanmax(finite_positive) - np.nanmin(finite_positive))
    return positive if positive_span < norm_span else normalized

def tile_lonlat_grid(z: int, x: int, y: int, size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    scale = 2 ** z
    cols = (np.arange(size, dtype="float64") + 0.5) / size
    rows = (np.arange(size, dtype="float64") + 0.5) / size
    xx, yy = np.meshgrid(x + cols, y + rows)
    lon = xx / scale * 360.0 - 180.0
    lat_rad = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * yy / scale)))
    lat = np.degrees(lat_rad)
    return lon, lat

def coordinate_lookup(ds: xr.Dataset) -> tuple[cKDTree, tuple[int, int], float, np.ndarray]:
    ln, lt = get_coordinates(ds)
    path = _CURRENT_FILE["path"]
    cached = (
        _DS_CACHE["path"] == path
        and _DS_CACHE["coord_tree"] is not None
        and _DS_CACHE["coord_shape"] == ln.shape
    )
    if cached:
        return (
            _DS_CACHE["coord_tree"],
            _DS_CACHE["coord_shape"],
            _DS_CACHE["coord_radius"],
            _DS_CACHE["coord_source_indices"],
        )

    lon_norm = normalize_longitudes(ln)
    valid = np.isfinite(lon_norm) & np.isfinite(lt)
    if not np.any(valid):
        raise ValueError("No valid coordinates found")

    points = np.column_stack([lon_norm[valid].ravel(), np.asarray(lt, dtype="float64")[valid].ravel()])
    tree = cKDTree(points)

    row_spacing = np.nanmedian(np.hypot(np.diff(lon_norm, axis=0), np.diff(lt, axis=0))) if ln.shape[0] > 1 else np.nan
    col_spacing = np.nanmedian(np.hypot(np.diff(lon_norm, axis=1), np.diff(lt, axis=1))) if ln.shape[1] > 1 else np.nan
    spacing_candidates = [float(v) for v in (row_spacing, col_spacing) if np.isfinite(v) and v > 0]
    radius = max(spacing_candidates) * 2.5 if spacing_candidates else 1.0

    flat_indices = np.flatnonzero(valid.ravel())
    _DS_CACHE["coord_tree"] = tree
    _DS_CACHE["coord_shape"] = ln.shape
    _DS_CACHE["coord_radius"] = radius
    _DS_CACHE["coord_source_indices"] = flat_indices
    return tree, ln.shape, radius, flat_indices

def tile_values_from_grid(ds: xr.Dataset, da: xr.DataArray, z: int, x: int, y: int) -> np.ndarray:
    values = np.asarray(da.values)
    if values.ndim != 2:
        values = np.squeeze(values)
    if values.ndim != 2:
        raise ValueError("Tile variable is not two-dimensional after slicing")

    tree, shape, radius, source_index_lookup = coordinate_lookup(ds)
    if values.shape != shape:
        raise ValueError(f"Data shape {values.shape} does not match coordinate shape {shape}")

    lon_grid, lat_grid = tile_lonlat_grid(z, x, y)
    query_points = np.column_stack([normalize_longitudes(lon_grid).ravel(), lat_grid.ravel()])
    distances, nearest = tree.query(query_points, workers=-1)
    source_indices = source_index_lookup[nearest]
    sampled = values.ravel()[source_indices].astype("float64")
    sampled[distances > radius] = np.nan
    return sampled.reshape((256, 256))

def values_to_png(values: np.ndarray, colormap: str, vmin: float | None, vmax: float | None) -> bytes:
    finite = np.isfinite(values)
    if not np.any(finite):
        return get_blank_tile()

    if vmin is None:
        vmin = float(np.nanpercentile(values, 2))
    if vmax is None:
        vmax = float(np.nanpercentile(values, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        vmin, vmax = float(np.nanmin(values)), float(np.nanmax(values))
    if vmin == vmax:
        vmax = vmin + 1.0

    normalized = np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)
    cmap = plt.get_cmap(colormap)
    rgba = (cmap(np.nan_to_num(normalized, nan=0.0)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

def find_da(ds: xr.Dataset, v_id: str, level: int = 0) -> xr.DataArray | None:
    if ds is None: return None

    if v_id == "CURRENT_SPD":
        u_da = find_da(ds, "CURRENT_U", level)
        v_da = find_da(ds, "CURRENT_V", level)
        if u_da is not None and v_da is not None:
            return np.sqrt(u_da**2 + v_da**2)

    if v_id == "CURRENT_U":
        for c in ("CURRENT_U", "UO", "uo", "water_u", "sea_water_x_velocity"):
            if c in ds:
                return ds[c]
        return None

    if v_id == "CURRENT_V":
        for c in ("CURRENT_V", "VO", "vo", "water_v", "sea_water_y_velocity"):
            if c in ds:
                return ds[c]
        return None

    # Custom handlers for multi-level fields
    if v_id == "T_LEV":
        if "T" not in ds or "P" not in ds or "PB" not in ds: return None
        t_pot = ds["T"].isel(bottom_top=level) + 300.0
        p_tot = ds["P"].isel(bottom_top=level) + ds["PB"].isel(bottom_top=level)
        temp_k = t_pot * (p_tot / 100000.0) ** (2.0 / 7.0)
        temp_c = temp_k - 273.15
        template = ds["T2"] if "T2" in ds else ds["T"].isel(bottom_top=0)
        return xr.DataArray(temp_c, dims=template.dims, coords=template.coords)

    if v_id == "U_LEV":
        if "U" not in ds or "T2" not in ds: return None
        u_stag = ds["U"].isel(bottom_top=level)
        u_val = 0.5 * (u_stag.values[..., :-1] + u_stag.values[..., 1:])
        template = ds["T2"]
        return xr.DataArray(u_val, dims=template.dims, coords=template.coords)

    if v_id == "V_LEV":
        if "V" not in ds or "T2" not in ds: return None
        v_stag = ds["V"].isel(bottom_top=level)
        v_val = 0.5 * (v_stag.values[..., :-1, :] + v_stag.values[..., 1:, :])
        template = ds["T2"]
        return xr.DataArray(v_val, dims=template.dims, coords=template.coords)

    if v_id == "WSPD_LEV":
        u_da = find_da(ds, "U_LEV", level)
        v_da = find_da(ds, "V_LEV", level)
        if u_da is not None and v_da is not None:
            return np.sqrt(u_da**2 + v_da**2)
        return None

    cfg = VARIABLE_CONFIG.get(v_id)
    if not cfg: return None
    for c in cfg["candidates"]:
        if c in ds:
            da = ds[c]
            if "bottom_top" in da.dims:
                l_idx = min(level, da.sizes["bottom_top"] - 1)
                da = da.isel(bottom_top=l_idx)
            elif "bottom_top_stag" in da.dims:
                l_idx = min(level, da.sizes["bottom_top_stag"] - 1)
                da = da.isel(bottom_top_stag=l_idx)
            return da
    return None

def variable_num_levels(ds: xr.Dataset, v_id: str, cfg: dict) -> int:
    if ds is None or len(ds.data_vars) == 0:
        return 1
    if v_id in ("T_LEV", "P_HYD", "WSPD_LEV", "REFL_10CM"):
        return ds.sizes.get("bottom_top", 1)
    for c in cfg["candidates"]:
        if c in ds:
            da = ds[c]
            if "bottom_top" in da.dims:
                return ds.sizes.get("bottom_top", 1)
            if "bottom_top_stag" in da.dims:
                return ds.sizes.get("bottom_top_stag", 1)
            break
    return 1

def variable_available(ds: xr.Dataset, v_id: str) -> bool:
    try:
        if v_id == "WSPD":
            return (find_da(ds, "U10") is not None and find_da(ds, "V10") is not None) or find_da(ds, "WSPD") is not None
        if v_id == "WSPD_LEV":
            return find_da(ds, "U_LEV") is not None and find_da(ds, "V_LEV") is not None
        if v_id == "CURRENT_SPD":
            return find_da(ds, "CURRENT_U") is not None and find_da(ds, "CURRENT_V") is not None
        return find_da(ds, v_id) is not None
    except Exception:
        return False

def dataset_time_count(ds: xr.Dataset) -> int:
    for d in ("Time", "time"):
        if d in ds.sizes:
            return int(ds.sizes[d])
    return 1

def parse_time_values(vals) -> list[int]:
    arr = np.asarray(vals)
    if arr.dtype.kind in ("S", "U"):
        raw_times = []
        if arr.ndim == 2:
            for row in arr:
                if row.dtype.kind == "S":
                    raw_times.append(b"".join(row).decode("utf-8").strip())
                else:
                    raw_times.append("".join(row.astype(str)).strip())
        else:
            for t in arr:
                raw_times.append(t.decode("utf-8").strip() if isinstance(t, bytes) else str(t).strip())

        parsed = []
        for t in raw_times:
            stamp = t.replace("_", " ")
            parsed.append(int(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp() * 1000))
        return parsed

    return [int(pd.to_datetime(t).timestamp() * 1000) for t in arr]

def nearest_grid_index(ds: xr.Dataset, lat: float, lon: float) -> tuple[int, int, np.ndarray, np.ndarray]:
    lons, lats = get_coordinates(ds)
    dist = (lats - lat)**2 + (lons - lon)**2
    j, i = np.unravel_index(np.argmin(dist), dist.shape)
    return int(j), int(i), lons, lats

def select_time_slice(da: xr.DataArray, t_idx: int) -> xr.DataArray:
    for d in ("Time", "time"):
        if d in da.dims:
            return da.isel({d: min(t_idx, da.sizes[d] - 1)})
    return da

def resolve_display_variable(ds: xr.Dataset, v_id: str, level: int = 0) -> tuple[xr.DataArray | None, dict | None]:
    if v_id in ("WIND", "WSPD"):
        if level > 0:
            da = find_da(ds, "WSPD_LEV", level)
        else:
            u, v = find_da(ds, "U10", level), find_da(ds, "V10", level)
            da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD", level)
        return da, VARIABLE_CONFIG.get("WSPD")
    if v_id == "WSPD_LEV":
        return find_da(ds, "WSPD_LEV", level), VARIABLE_CONFIG.get("WSPD_LEV")
    return find_da(ds, v_id, level), VARIABLE_CONFIG.get(v_id)

def dataset_bounds(lons: np.ndarray, lats: np.ndarray) -> list[float]:
    lon_values = np.asarray(lons, dtype="float64")
    lat_values = np.asarray(lats, dtype="float64")
    finite_lon = lon_values[np.isfinite(lon_values)]
    finite_lat = lat_values[np.isfinite(lat_values)]
    if finite_lon.size == 0 or finite_lat.size == 0:
        raise ValueError("No finite coordinates found")

    display_lon = continuous_longitudes(finite_lon)

    return [
        float(np.nanmin(display_lon)),
        float(np.nanmin(finite_lat)),
        float(np.nanmax(display_lon)),
        float(np.nanmax(finite_lat)),
    ]

def readiness_report() -> tuple[dict, int]:
    checks: dict[str, dict] = {}
    dataset_path = resolve_dataset_path()

    checks["dataset"] = {
        "ok": dataset_path is not None,
        "path": dataset_path,
        "configuredPath": _CURRENT_FILE["path"],
    }
    if dataset_path is None:
        return {"status": "not_ready", "checks": checks}, 503

    try:
        ds = get_dataset()
        checks["openDataset"] = {"ok": len(ds.data_vars) > 0, "variables": len(ds.data_vars)}
    except Exception as e:
        checks["openDataset"] = {"ok": False, "error": str(e)}
        return {"status": "not_ready", "checks": checks}, 503

    try:
        lons, lats = get_coordinates(ds)
        checks["coordinates"] = {
            "ok": True,
            "shape": list(lons.shape),
            "bounds": dataset_bounds(lons, lats),
        }
    except Exception as e:
        checks["coordinates"] = {"ok": False, "error": str(e)}

    time_count = dataset_time_count(ds)
    checks["time"] = {"ok": time_count > 0, "count": time_count}

    available = [k for k in VARIABLE_CONFIG if variable_available(ds, k)]
    checks["variables"] = {"ok": len(available) > 0, "count": len(available), "available": available}

    ready = all(check.get("ok", False) for check in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}, 200 if ready else 503

@app.route("/health")
def health(): return jsonify(status="ok")

@app.route("/ready")
def ready():
    body, status_code = readiness_report()
    return jsonify(body), status_code

@app.route("/version")
def version():
    dataset_path = resolve_dataset_path()
    return jsonify(
        service="maritime-platform-backend",
        version=BUILD_VERSION,
        gitSha=BUILD_SHA,
        buildDate=BUILD_DATE,
        dataset=Path(dataset_path).name if dataset_path else None,
    )

@app.route("/variables")
def get_variables():
    res = []
    ds = get_dataset()
    for k, v in VARIABLE_CONFIG.items():
        available = variable_available(ds, k)
        num_levels = variable_num_levels(ds, k, v) if available else 1
        res.append({
            "id": k,
            "name": v["name"],
            "units": v["units"],
            "description": v.get("description", ""),
            "colormap": v["colormap"],
            "numLevels": num_levels,
            "category": v.get("category", "weather"),
            "available": available,
        })
    return jsonify(res)

@app.route("/time_points")
def get_time_points():
    try:
        ds = get_dataset()
        for c in ("XTIME", "Times", "time"):
            if c in ds:
                return jsonify(parse_time_values(ds[c].values))
    except: pass
    return jsonify([])

@app.route("/model_summary")
def model_summary():
    try:
        ds = get_dataset()
        ln, lt = get_coordinates(ds)
        stem = Path(_CURRENT_FILE["path"]).stem
        time_count = dataset_time_count(ds)
        available = [k for k in VARIABLE_CONFIG if variable_available(ds, k)]
        marine_available = [
            k for k in available
            if VARIABLE_CONFIG[k].get("category") == "marine"
        ]
        cog_count = 0
        cog_root = Path(COG_ROOT)
        for v_id in VARIABLE_CONFIG:
            for t in range(time_count):
                if (cog_root / v_id / f"{stem}_t{t}.tif").exists():
                    cog_count += 1
        return jsonify({
            "file": Path(_CURRENT_FILE["path"]).name,
            "path": _CURRENT_FILE["path"],
            "timeCount": time_count,
            "bounds": dataset_bounds(ln, lt),
            "availableVariables": len(available),
            "marineVariables": len(marine_available),
            "cogTilesReady": cog_count,
            "etl": get_etl_status(),
        })
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/variable_stats")
def variable_stats():
    try:
        t_idx, v_id = request.args.get("time", 0, int), request.args.get("variable", "T2", str)
        level = request.args.get("level", 0, int)
        ds = get_dataset()
        da, cfg = resolve_display_variable(ds, v_id, level)

        if da is None or cfg is None: return jsonify(error="Not found"), 404

        da = select_time_slice(da, t_idx)

        vals = da.values.astype("float64") * cfg["scale"] + cfg["offset"]
        lons, lats = get_coordinates(ds)

        return jsonify({
            "valueRange": [float(np.nanmin(vals)), float(np.nanmax(vals))],
            "bounds": dataset_bounds(lons, lats),
            "colormap": cfg["colormap"], "units": cfg["units"], "name": cfg["name"]
        })
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/probe")
def probe_value():
    try:
        lat, lon, t_idx, v_id = request.args.get("lat", type=float), request.args.get("lon", type=float), request.args.get("time", 0, int), request.args.get("variable", "T2", str)
        level = request.args.get("level", 0, int)
        ds = get_dataset()

        # Determine time step
        ds_t = ds
        for d in ("Time", "time"):
            if d in ds.dims: ds_t = ds.isel({d: min(t_idx, ds.sizes[d]-1)}); break

        j, i, _, _ = nearest_grid_index(ds, lat, lon)

        if v_id in ("WSPD", "WIND", "WSPD_LEV", "WIND_LEV"):
            if level > 0 or v_id in ("WSPD_LEV", "WIND_LEV"):
                u_da = find_da(ds_t, "U_LEV", level)
                v_da = find_da(ds_t, "V_LEV", level)
            else:
                u_da, v_da = find_da(ds_t, "U10", level), find_da(ds_t, "V10", level)
                if u_da is None or v_da is None:
                    u_da = find_da(ds_t, "U_LEV", level)
                    v_da = find_da(ds_t, "V_LEV", level)

            if u_da is not None and v_da is not None:
                u, v = float(u_da.values[j, i]), float(v_da.values[j, i])
                speed = np.sqrt(u**2 + v**2)
                # Meteorological direction (from where wind blows)
                direction = (np.degrees(np.arctan2(u, v)) + 180) % 360
                return jsonify({
                    "value": round(speed, 2), "direction": round(direction, 0),
                    "units": "m/s", "variable": "風場", "lat": lat, "lon": lon
                })

        da = find_da(ds_t, v_id, level)
        cfg = VARIABLE_CONFIG.get(v_id)
        if da is None or cfg is None: return jsonify(error="Missing"), 404
        val = da.values[j, i]
        return jsonify({"value": round(float(val) * cfg["scale"] + cfg["offset"], 2), "units": cfg["units"], "variable": cfg["name"], "lat": lat, "lon": lon})
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/time_series")
def time_series():
    try:
        lat = request.args.get("lat", type=float)
        lon = request.args.get("lon", type=float)
        v_id = request.args.get("variable", "T2", str)
        level = request.args.get("level", 0, int)
        if lat is None or lon is None:
            return jsonify(error="lat and lon are required"), 400

        ds = get_dataset()
        da, cfg = resolve_display_variable(ds, v_id, level)
        if da is None or cfg is None:
            return jsonify(error="Variable not found"), 404

        j, i, lons, lats = nearest_grid_index(ds, lat, lon)
        time_dim = next((d for d in ("Time", "time") if d in da.dims), None)
        values = []
        if time_dim:
            for t_idx in range(da.sizes[time_dim]):
                val = da.isel({time_dim: t_idx}).values[j, i]
                if np.isfinite(val):
                    values.append(round(float(val) * cfg["scale"] + cfg["offset"], 3))
                else:
                    values.append(None)
        else:
            val = da.values[j, i]
            values.append(round(float(val) * cfg["scale"] + cfg["offset"], 3) if np.isfinite(val) else None)

        return jsonify({
            "values": values,
            "units": cfg["units"],
            "variable": cfg["name"],
            "lat": lat,
            "lon": lon,
            "gridLat": round(float(lats[j, i]), 6),
            "gridLon": round(float(lons[j, i]), 6),
            "level": level,
        })
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/contours")
def get_contours():
    try:
        v_id, t_idx = request.args.get("variable", "PSFC", str), request.args.get("time", 0, int)
        level = request.args.get("level", 0, int)
        ds = get_dataset()
        if v_id in ("WSPD", "WIND"):
            if level > 0:
                da = find_da(ds, "WSPD_LEV", level)
            else:
                u, v = find_da(ds, "U10", level), find_da(ds, "V10", level)
                da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD", level)
        elif v_id == "WSPD_LEV":
            da = find_da(ds, "WSPD_LEV", level)
        else:
            da = find_da(ds, v_id, level)

        cfg = VARIABLE_CONFIG.get(v_id)
        if da is None or cfg is None: return jsonify(error="Not found"), 404

        for d in ("Time", "time"):
            if d in da.dims: da = da.isel({d: min(t_idx, da.sizes[d]-1)}); break
        vals = da.values.astype("float64") * cfg["scale"] + cfg["offset"]
        v_min, v_max = np.nanmin(vals), np.nanmax(vals)
        interval = 4.0 if v_id == "PSFC" else 2.0
        levels = np.arange(np.floor(v_min/interval)*interval, v_max, interval)
        ln, lt = get_coordinates(ds)

        with render_lock:
            fig, ax = plt.subplots(); cs = ax.contour(ln, lt, vals, levels=levels)
            features = []
            for i, col in enumerate(cs.collections):
                for path in col.get_paths():
                    for line in path.to_polygons(closed_only=False):
                        coords = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in line]
                        if len(coords) > 1: features.append(geojson.Feature(geometry=geojson.LineString(coords), properties={"value": float(cs.levels[i])}))
            plt.close(fig)

        return jsonify(geojson.FeatureCollection(features))
    except Exception as e: return jsonify(error=str(e)), 500

from wind_texture import encode_wind_to_png, create_coordinate_texture
from etl_bridge import get_etl_status, trigger_etl_for_file
from tile_cache import clear_all_caches, coords_texture_cache, tile_cache, wind_texture_cache
from flask import make_response

@app.route("/coords_texture", methods=["GET"])
def get_coords_texture():
    try:
        t_idx = request.args.get("time", 0, int)
        file_stem = Path(_CURRENT_FILE["path"]).stem
        cache_key = (file_stem, "coords", t_idx)
        cached = coords_texture_cache.get(cache_key)
        if cached is not None:
            response = make_response(send_file(io.BytesIO(cached), mimetype="application/octet-stream"))
            ds = get_dataset()
            ln, lt = get_coordinates(ds)
            display_lons = continuous_longitudes(ln)
            response.headers["X-Coords-Lon-Range"] = f"{float(np.nanmin(display_lons)):.6f},{float(np.nanmax(display_lons)):.6f}"
            response.headers["X-Coords-Lat-Range"] = f"{float(np.nanmin(lt)):.6f},{float(np.nanmax(lt)):.6f}"
            response.headers["X-Coords-Grid-Size"] = f"{ln.shape[1]},{ln.shape[0]}"
            response.headers["Access-Control-Expose-Headers"] = (
                "X-Coords-Lon-Range,X-Coords-Lat-Range,X-Coords-Grid-Size"
            )
            return response

        ds = get_dataset()
        ln, lt = get_coordinates(ds)

        display_lons = continuous_longitudes(ln)
        buf, metadata = create_coordinate_texture(display_lons, lt)

        response = make_response(send_file(io.BytesIO(buf), mimetype='application/octet-stream'))
        response.headers['X-Coords-Lon-Range'] = f"{metadata['min_lon']:.6f},{metadata['max_lon']:.6f}"
        response.headers['X-Coords-Lat-Range'] = f"{metadata['min_lat']:.6f},{metadata['max_lat']:.6f}"
        response.headers['X-Coords-Grid-Size'] = f"{metadata['width']},{metadata['height']}"
        response.headers['Access-Control-Expose-Headers'] = 'X-Coords-Lon-Range,X-Coords-Lat-Range,X-Coords-Grid-Size'

        coords_texture_cache.set(cache_key, buf)
        return response
    except Exception as e:
        app.logger.error(f"coords error: {e}", exc_info=True)
        return jsonify(error=str(e)), 500

@app.route("/wind_texture")
def get_wind_texture():
    try:
        import json as json_mod

        t_idx = request.args.get("time", 0, int)
        level = request.args.get("level", 0, int)
        file_stem = Path(_CURRENT_FILE["path"]).stem
        want_meta = request.args.get("metadata", "false").lower() == "true"
        cache_key = (file_stem, f"wind_meta_l{level}" if want_meta else f"wind_png_l{level}", t_idx)

        cached = wind_texture_cache.get(cache_key)
        if cached is not None:
            if want_meta:
                return jsonify(json_mod.loads(cached.decode("utf-8")))
            return send_file(io.BytesIO(cached), mimetype="image/png")

        ds = get_dataset()
        if level > 0:
            u_da = find_da(ds, "U_LEV", level)
            v_da = find_da(ds, "V_LEV", level)
        else:
            u_da = find_da(ds, "U10")
            v_da = find_da(ds, "V10")
            if u_da is None or v_da is None:
                u_da = find_da(ds, "U_LEV", level)
                v_da = find_da(ds, "V_LEV", level)

        if u_da is None or v_da is None: return jsonify(error="Wind missing"), 404
        for d in ("Time", "time"):
            if d in u_da.dims: u_da, v_da = u_da.isel({d: min(t_idx, u_da.sizes[d]-1)}), v_da.isel({d: min(t_idx, v_da.sizes[d]-1)}); break
        u_v, v_v = u_da.values.astype("float32"), v_da.values.astype("float32")
        ln, lt = get_coordinates(ds)
        buf, meta = encode_wind_to_png(u_v, v_v)
        if want_meta:
            payload = {
                "uMin": meta["u_min"], "uMax": meta["u_max"],
                "vMin": meta["v_min"], "vMax": meta["v_max"],
                "width": meta["width"], "height": meta["height"],
                "bounds": dataset_bounds(ln, lt),
            }
            raw = json_mod.dumps(payload).encode("utf-8")
            wind_texture_cache.set(cache_key, raw)
            return jsonify(payload)
        png_bytes = buf.getvalue()
        wind_texture_cache.set(cache_key, png_bytes)
        return send_file(io.BytesIO(png_bytes), mimetype="image/png")
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/wind_data")
def get_wind_data():
    try:
        t_idx = request.args.get("time", 0, int)
        level = request.args.get("level", 0, int)
        max_points = max(500, min(request.args.get("max_points", 14000, int), 50000))

        ds = get_dataset()
        if level > 0:
            u_da = find_da(ds, "U_LEV", level)
            v_da = find_da(ds, "V_LEV", level)
        else:
            u_da = find_da(ds, "U10")
            v_da = find_da(ds, "V10")
            if u_da is None or v_da is None:
                u_da = find_da(ds, "U_LEV", level)
                v_da = find_da(ds, "V_LEV", level)

        if u_da is None or v_da is None:
            return jsonify(error="Wind missing"), 404

        u_da = select_time_slice(u_da, t_idx)
        v_da = select_time_slice(v_da, t_idx)
        u_v = np.asarray(u_da.values, dtype="float32").squeeze()
        v_v = np.asarray(v_da.values, dtype="float32").squeeze()
        ln, lt = get_coordinates(ds)
        display_lons = continuous_longitudes(ln)

        if u_v.shape != display_lons.shape or v_v.shape != display_lons.shape:
            return jsonify(error="Wind grid shape does not match coordinates"), 500

        stride = max(1, int(np.ceil(np.sqrt(u_v.size / max_points))))
        lon_s = display_lons[::stride, ::stride]
        lat_s = lt[::stride, ::stride]
        u_s = u_v[::stride, ::stride]
        v_s = v_v[::stride, ::stride]
        valid = np.isfinite(lon_s) & np.isfinite(lat_s) & np.isfinite(u_s) & np.isfinite(v_s)

        points = [
            {
                "lon": round(float(lon), 5),
                "lat": round(float(lat), 5),
                "u": round(float(u), 4),
                "v": round(float(v), 4),
            }
            for lon, lat, u, v in zip(lon_s[valid].ravel(), lat_s[valid].ravel(), u_s[valid].ravel(), v_s[valid].ravel())
        ]

        return jsonify({
            "points": points,
            "bounds": dataset_bounds(ln, lt),
            "stride": stride,
            "sourcePoints": int(u_v.size),
        })
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/netcdf_files")
def list_netcdf_files():
    try:
        files = [f for f in Path(DATA_DIR).iterdir() if is_dataset_candidate(f)]
        res = []
        for f in files:
            parts = f.name.split("_")
            res.append({"filename": f.name, "path": str(f), "domain": parts[1].upper() if len(parts) > 1 else "WRF", "date": f.name, "size_mb": round(f.stat().st_size / (1024 * 1024), 1), "is_current": str(f) == _CURRENT_FILE["path"]})
        return jsonify({"files": res, "current": _CURRENT_FILE["path"]})
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/etl/status")
def etl_status():
    return jsonify(get_etl_status())


@app.route("/cache/stats")
def cache_stats():
    import os

    workers = os.getenv("GUNICORN_WORKERS", "1")
    return jsonify(
        tile=tile_cache.stats(),
        wind_texture=wind_texture_cache.stats(),
        coords_texture=coords_texture_cache.stats(),
        note="LRU is per Gunicorn worker process; use GUNICORN_WORKERS=1 for dev cache testing",
        gunicorn_workers=workers,
    )

@app.route("/metrics")
def metrics():
    with metrics_lock:
        total = REQUEST_METRICS["total"]
        latency_sum = REQUEST_METRICS["latency_seconds_sum"]
        status_classes = dict(REQUEST_METRICS["status_classes"])
        endpoints = dict(REQUEST_METRICS["endpoints"])
        rate_limited = REQUEST_METRICS["rate_limited"]

    cache = tile_cache.stats()
    wind = wind_texture_cache.stats()
    coords = coords_texture_cache.stats()
    lines = [
        "# HELP maritime_http_requests_total Total HTTP requests handled by this worker.",
        "# TYPE maritime_http_requests_total counter",
        f"maritime_http_requests_total {total}",
        "# HELP maritime_http_request_duration_seconds_sum Total HTTP request latency in seconds.",
        "# TYPE maritime_http_request_duration_seconds_sum counter",
        f"maritime_http_request_duration_seconds_sum {latency_sum:.6f}",
        "# HELP maritime_http_rate_limited_total Total HTTP requests rejected by the built-in rate limiter.",
        "# TYPE maritime_http_rate_limited_total counter",
        f"maritime_http_rate_limited_total {rate_limited}",
        "# HELP maritime_http_requests_by_status_class_total HTTP requests by status class.",
        "# TYPE maritime_http_requests_by_status_class_total counter",
    ]
    for status_class, count in sorted(status_classes.items()):
        lines.append(f'maritime_http_requests_by_status_class_total{{status_class="{status_class}"}} {count}')

    lines.extend([
        "# HELP maritime_http_requests_by_endpoint_total HTTP requests by Flask route.",
        "# TYPE maritime_http_requests_by_endpoint_total counter",
    ])
    for endpoint, count in sorted(endpoints.items()):
        lines.append(f'maritime_http_requests_by_endpoint_total{{endpoint="{endpoint}"}} {count}')

    lines.extend([
        "# HELP maritime_tile_cache_entries Current tile cache entries.",
        "# TYPE maritime_tile_cache_entries gauge",
        f"maritime_tile_cache_entries {cache['size']}",
        "# HELP maritime_tile_cache_hit_rate Tile cache hit rate for this worker.",
        "# TYPE maritime_tile_cache_hit_rate gauge",
        f"maritime_tile_cache_hit_rate {cache['hit_rate']}",
        "# HELP maritime_wind_cache_entries Current wind texture cache entries.",
        "# TYPE maritime_wind_cache_entries gauge",
        f"maritime_wind_cache_entries {wind['size']}",
        "# HELP maritime_coords_cache_entries Current coordinate texture cache entries.",
        "# TYPE maritime_coords_cache_entries gauge",
        f"maritime_coords_cache_entries {coords['size']}",
    ])
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")


@app.route("/netcdf_files/select", methods=["POST"])
def select_netcdf_file():
    payload = request.get_json(silent=True) or {}
    path = payload.get("path")
    selected = resolve_selectable_dataset(path) if path else None
    if selected is None:
        return jsonify(error="Not found"), 404
    path = str(selected)
    _CURRENT_FILE["path"] = path
    _DS_CACHE["ds"] = None
    clear_all_caches()
    etl_started = trigger_etl_for_file(path, COG_ROOT)
    return jsonify(status="success", current=path, etl={"started": etl_started})

def _render_tile_png(
    v_id: str,
    t_idx: int,
    z: int,
    x: int,
    y: int,
    vmin: float | None,
    vmax: float | None,
    level: int = 0,
) -> bytes:
    """Render one map tile PNG (caller must hold render_lock)."""
    ds = get_dataset()
    if v_id in ("WSPD", "WIND"):
        if level > 0:
            da = find_da(ds, "WSPD_LEV", level)
        else:
            u, v = find_da(ds, "U10", level), find_da(ds, "V10", level)
            da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD", level)
    elif v_id == "WSPD_LEV":
        da = find_da(ds, "WSPD_LEV", level)
    else:
        da = find_da(ds, v_id, level)

    if da is None:
        raise ValueError("Variable not found")

    cfg = VARIABLE_CONFIG.get(v_id, {})
    colormap = cfg.get("colormap", "viridis")

    for d in ("Time", "time"):
        if d in da.dims:
            da = da.isel({d: min(t_idx, da.sizes[d] - 1)})
            break

    ln, lt = get_coordinates(ds)
    tile_bounds = mercantile.bounds(x, y, z)

    lon_norm = normalize_longitudes(ln)
    west_norm = normalize_longitudes(np.array([tile_bounds.west]))[0]
    east_norm = normalize_longitudes(np.array([tile_bounds.east]))[0]
    if east_norm >= west_norm:
        in_lon = (lon_norm >= west_norm) & (lon_norm <= east_norm)
    else:
        in_lon = (lon_norm >= west_norm) | (lon_norm <= east_norm)
    in_lat = (lt >= tile_bounds.south) & (lt <= tile_bounds.north)
    if not np.any(in_lon & in_lat):
        return get_blank_tile()

    vals = tile_values_from_grid(ds, da, z, x, y)
    vals = vals.astype("float64") * cfg.get("scale", 1.0) + cfg.get("offset", 0.0)
    return values_to_png(vals, colormap, vmin, vmax)


@app.route("/tiles/<int:z>/<int:x>/<int:y>")
def get_tile(z, x, y):
    """
    Dynamic tile renderer for NetCDF/GRIB2 variables.
    Used as fallback when COGs are missing.
    """
    try:
        v_id = request.args.get("variable", "T2")
        t_idx = request.args.get("time", 0, int)
        level = request.args.get("level", 0, int)
        vmin = request.args.get("vmin", type=float)
        vmax = request.args.get("vmax", type=float)

        file_stem = Path(_CURRENT_FILE["path"]).stem
        cache_key = tile_cache.make_key(file_stem, v_id, t_idx, z, x, y, vmin, vmax, level)
        def _render() -> bytes:
            with render_lock:
                return _render_tile_png(v_id, t_idx, z, x, y, vmin, vmax, level)

        png_bytes = tile_cache.get_or_set(cache_key, _render)
        return send_file(io.BytesIO(png_bytes), mimetype="image/png")
    except Exception as e:
        app.logger.error(f"Tile error: {e}")
        return str(e), 500

@app.route("/cog_manifest")
def cog_manifest():
    try:
        ds = get_dataset()
        ln, lt = get_coordinates(ds)
        bounds = dataset_bounds(ln, lt)
        manifest = {}
        stem = Path(_CURRENT_FILE["path"]).stem
        cog_root = Path(COG_ROOT)
        for v_id in VARIABLE_CONFIG:
            paths = [
                f"{COG_ROOT}/{v_id}/{stem}_t{t}.tif"
                for t in range(dataset_time_count(ds))
                if (cog_root / v_id / f"{stem}_t{t}.tif").exists()
            ]
            if paths: manifest[v_id] = paths
        return jsonify({"variables": manifest, "bounds": bounds})
    except Exception as e: return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
