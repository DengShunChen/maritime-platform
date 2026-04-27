"""
Maritime Platform - Metadata API (Wind Support Update)
"""
from __future__ import annotations
import logging
import os
import io
import threading
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geojson
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.DEBUG)

render_lock = threading.Lock()

DATA_DIR = os.getenv("NETCDF_DATA_DIR", "data")
DEFAULT_NETCDF = os.getenv("NETCDF_PATH", "data/wrfout_d01_2025-11-13_00:00:00")
COG_ROOT = os.getenv("COG_ROOT", "/cog")

_CURRENT_FILE: dict[str, str] = {"path": DEFAULT_NETCDF}

VARIABLE_CONFIG: dict[str, dict] = {
    "PSFC":     {"name": "表面氣壓", "units": "hPa", "colormap": "viridis", "scale": 0.01, "offset": 0.0, "candidates": ["PSFC", "sp", "P"]},
    "T2":       {"name": "2米溫度", "units": "°C", "colormap": "RdYlBu_r", "scale": 1.0, "offset": -273.15, "candidates": ["T2", "T"]},
    "RAINC":    {"name": "對流降水", "units": "mm", "colormap": "YlGnBu", "scale": 1.0, "offset": 0.0, "candidates": ["RAINC", "tp"]},
    "RAINNC":   {"name": "網格降水", "units": "mm", "colormap": "YlGnBu", "scale": 1.0, "offset": 0.0, "candidates": ["RAINNC"]},
    "U10":      {"name": "U風分量", "units": "m/s", "colormap": "RdBu_r", "scale": 1.0, "offset": 0.0, "candidates": ["U10", "U"]},
    "V10":      {"name": "V風分量", "units": "m/s", "colormap": "RdBu_r", "scale": 1.0, "offset": 0.0, "candidates": ["V10", "V"]},
    "REFD_MAX": {"name": "雷達反射率", "units": "dBZ", "colormap": "gist_ncar", "scale": 1.0, "offset": 0.0, "candidates": ["REFD_MAX", "refd"]},
    "WSPD":     {"name": "風速", "units": "m/s", "colormap": "plasma", "scale": 1.0, "offset": 0.0, "candidates": ["WSPD", "wspd"]},
}

_DS_CACHE: dict = {"path": None, "mtime": None, "ds": None}

def _open_grib2_layer(path: str, type_of_level: str) -> xr.Dataset | None:
    try:
        return xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"typeOfLevel": type_of_level}, "indexpath": ""})
    except: return None

def get_dataset() -> xr.Dataset:
    path = _CURRENT_FILE["path"]
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
    return _DS_CACHE["ds"]

def find_da(ds: xr.Dataset, v_id: str) -> xr.DataArray | None:
    if ds is None or len(ds.data_vars) == 0: return None
    cfg = VARIABLE_CONFIG.get(v_id)
    if not cfg: return None
    for c in cfg["candidates"]:
        if c in ds:
            da = ds[c]
            if "bottom_top" in da.dims: da = da.isel(bottom_top=0)
            if "bottom_top_stag" in da.dims: da = da.isel(bottom_top_stag=0)
            return da
    return None

@app.route("/health")
def health(): return jsonify(status="ok")

@app.route("/variables")
def get_variables():
    return jsonify([{"id": k, "name": v["name"], "units": v["units"], "colormap": v["colormap"]} for k, v in VARIABLE_CONFIG.items()])

@app.route("/time_points")
def get_time_points():
    try:
        ds = get_dataset()
        for c in ("XTIME", "Times", "time"):
            if c in ds:
                vals = ds[c].values
                if vals.dtype.kind in ('S', 'U'):
                    times = [datetime.strptime(t.decode('utf-8').replace('_', ' '), '%Y-%m-%d %H:%M:%S') for t in vals]
                    return jsonify([int(t.timestamp() * 1000) for t in times])
                return jsonify([int(pd.to_datetime(t).timestamp() * 1000) for t in vals])
    except: pass
    return jsonify([])

@app.route("/variable_stats")
def variable_stats():
    try:
        t_idx, v_id = request.args.get("time", 0, int), request.args.get("variable", "T2", str)
        ds = get_dataset()
        if v_id in ("WSPD", "WIND"):
            u, v = find_da(ds, "U10"), find_da(ds, "V10")
            da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD")
        else:
            da = find_da(ds, v_id)
            
        cfg = VARIABLE_CONFIG.get(v_id)
        if da is None or cfg is None: return jsonify(error="Not found"), 404
        
        for d in ("Time", "time"):
            if d in da.dims: da = da.isel({d: min(t_idx, da.sizes[d]-1)}); break
        
        vals = da.values.astype("float64") * cfg["scale"] + cfg["offset"]
        lons, lats = ds["XLONG"].values, ds["XLAT"].values
        if lons.ndim == 3: lons, lats = lons[0], lats[0]
        
        return jsonify({
            "valueRange": [float(np.nanmin(vals)), float(np.nanmax(vals))],
            "bounds": [float(np.nanmin(lons)), float(np.nanmin(lats)), float(np.nanmax(lons)), float(np.nanmax(lats))],
            "colormap": cfg["colormap"], "units": cfg["units"], "name": cfg["name"]
        })
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/probe")
def probe_value():
    try:
        lat, lon, t_idx, v_id = request.args.get("lat", type=float), request.args.get("lon", type=float), request.args.get("time", 0, int), request.args.get("variable", "T2", str)
        ds = get_dataset()
        
        # Determine time step
        ds_t = ds
        for d in ("Time", "time"):
            if d in ds.dims: ds_t = ds.isel({d: min(t_idx, ds.sizes[d]-1)}); break

        lons, lats = ds["XLONG"].values, ds["XLAT"].values
        if lons.ndim == 3: lons, lats = lons[0], lats[0]
        
        dist = (lats - lat)**2 + (lons - lon)**2
        j, i = np.unravel_index(np.argmin(dist), dist.shape)
        
        if v_id in ("WSPD", "WIND"):
            u_da, v_da = find_da(ds_t, "U10"), find_da(ds_t, "V10")
            if u_da is not None and v_da is not None:
                u, v = float(u_da.values[j, i]), float(v_da.values[j, i])
                speed = np.sqrt(u**2 + v**2)
                # Meteorological direction (from where wind blows)
                direction = (np.degrees(np.arctan2(u, v)) + 180) % 360
                return jsonify({
                    "value": round(speed, 2), "direction": round(direction, 0),
                    "units": "m/s", "variable": "風場", "lat": lat, "lon": lon
                })

        da = find_da(ds_t, v_id)
        cfg = VARIABLE_CONFIG.get(v_id)
        if da is None or cfg is None: return jsonify(error="Missing"), 404
        val = da.values[j, i]
        return jsonify({"value": round(float(val) * cfg["scale"] + cfg["offset"], 2), "units": cfg["units"], "variable": cfg["name"], "lat": lat, "lon": lon})
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/contours")
def get_contours():
    try:
        v_id, t_idx = request.args.get("variable", "PSFC", str), request.args.get("time", 0, int)
        ds = get_dataset()
        if v_id in ("WSPD", "WIND"):
            u, v = find_da(ds, "U10"), find_da(ds, "V10")
            da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD")
        else:
            da = find_da(ds, v_id)
            
        cfg = VARIABLE_CONFIG.get(v_id)
        if da is None or cfg is None: return jsonify(error="Not found"), 404
        
        for d in ("Time", "time"):
            if d in da.dims: da = da.isel({d: min(t_idx, da.sizes[d]-1)}); break
        vals = da.values.astype("float64") * cfg["scale"] + cfg["offset"]
        v_min, v_max = np.nanmin(vals), np.nanmax(vals)
        interval = 4.0 if v_id == "PSFC" else 2.0
        levels = np.arange(np.floor(v_min/interval)*interval, v_max, interval)
        ln, lt = ds["XLONG"].values, ds["XLAT"].values
        if ln.ndim == 3: ln, lt = ln[0], lt[0]
        
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
from flask import make_response

@app.route("/coords_texture", methods=["GET"])
def get_coords_texture():
    try:
        t_idx = request.args.get("time", 0, int)
        ds = get_dataset()
        # Find any variable just to get the coordinate grid
        da = find_da(ds, "T2")
        if da is None:
            da = find_da(ds, "U10")
        if da is None: return jsonify(error="No variable found to extract coords"), 404
        
        for d in ("Time", "time"):
            if d in da.dims: da = da.isel({d: min(t_idx, da.sizes[d]-1)}); break
            
        lons_da = ds.coords.get("XLONG", ds.coords.get("longitude"))
        lats_da = ds.coords.get("XLAT", ds.coords.get("latitude"))
        ln, lt = lons_da.values, lats_da.values
        if ln.ndim == 3: ln, lt = ln[0], lt[0]
        
        buf, metadata = create_coordinate_texture(ln, lt)
        
        response = make_response(send_file(io.BytesIO(buf), mimetype='application/octet-stream'))
        response.headers['X-Coords-Lon-Range'] = f"{metadata['min_lon']:.6f},{metadata['max_lon']:.6f}"
        response.headers['X-Coords-Lat-Range'] = f"{metadata['min_lat']:.6f},{metadata['max_lat']:.6f}"
        response.headers['X-Coords-Grid-Size'] = f"{metadata['width']},{metadata['height']}"
        response.headers['Access-Control-Expose-Headers'] = 'X-Coords-Lon-Range,X-Coords-Lat-Range,X-Coords-Grid-Size'
        
        return response
    except Exception as e:
        app.logger.error(f"coords error: {e}", exc_info=True)
        return jsonify(error=str(e)), 500

@app.route("/wind_texture")
def get_wind_texture():
    try:
        t_idx = request.args.get("time", 0, int)
        ds = get_dataset()
        u_da, v_da = find_da(ds, "U10"), find_da(ds, "V10")
        if u_da is None or v_da is None: return jsonify(error="Wind missing"), 404
        for d in ("Time", "time"):
            if d in u_da.dims: u_da, v_da = u_da.isel({d: min(t_idx, u_da.sizes[d]-1)}), v_da.isel({d: min(t_idx, u_da.sizes[d]-1)}); break
        u_v, v_v = u_da.values.astype("float32"), v_da.values.astype("float32")
        ln, lt = ds["XLONG"].values, ds["XLAT"].values
        if ln.ndim == 3: ln, lt = ln[0], lt[0]
        buf, meta = encode_wind_to_png(u_v, v_v)
        if request.args.get("metadata", "false").lower() == "true":
            return jsonify({"uMin": meta['u_min'], "uMax": meta['u_max'], "vMin": meta['v_min'], "vMax": meta['v_max'], "width": meta['width'], "height": meta['height'], "bounds": [float(np.nanmin(ln)), float(np.nanmin(lt)), float(np.nanmax(ln)), float(np.nanmax(lt))]})
        return send_file(io.BytesIO(buf.getvalue()), mimetype='image/png')
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/netcdf_files")
def list_netcdf_files():
    try:
        files = [f for f in Path(DATA_DIR).iterdir() if f.is_file() and not f.name.startswith(".")]
        res = []
        for f in files:
            parts = f.name.split("_")
            res.append({"filename": f.name, "path": str(f), "domain": parts[1].upper() if len(parts) > 1 else "WRF", "date": f.name, "size_mb": round(f.stat().st_size / (1024 * 1024), 1), "is_current": str(f) == _CURRENT_FILE["path"]})
        return jsonify({"files": res, "current": _CURRENT_FILE["path"]})
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/netcdf_files/select", methods=["POST"])
def select_netcdf_file():
    path = request.json.get("path")
    if not path or not Path(path).exists(): return jsonify(error="Not found"), 404
    _CURRENT_FILE["path"] = path; _DS_CACHE["ds"] = None
    return jsonify(status="success", current=path)

@app.route("/tiles/<int:z>/<int:x>/<int:y>")
def get_tile(z, x, y):
    """
    Dynamic tile renderer for NetCDF/GRIB2 variables.
    Used as fallback when COGs are missing.
    """
    try:
        v_id = request.args.get("variable", "T2")
        t_idx = request.args.get("time", 0, int)
        vmin = request.args.get("vmin", type=float)
        vmax = request.args.get("vmax", type=float)

        ds = get_dataset()
        if v_id in ("WSPD", "WIND"):
            u, v = find_da(ds, "U10"), find_da(ds, "V10")
            da = np.sqrt(u**2 + v**2) if (u is not None and v is not None) else find_da(ds, "WSPD")
        else:
            da = find_da(ds, v_id)

        if da is None: return "Variable not found", 404

        cfg = VARIABLE_CONFIG.get(v_id, {})
        colormap = cfg.get("colormap", "viridis")
        
        # Select time
        for d in ("Time", "time"):
            if d in da.dims: da = da.isel({d: min(t_idx, da.sizes[d]-1)}); break
            
        # Get data values and apply scale/offset
        vals = da.values.astype("float64") * cfg.get("scale", 1.0) + cfg.get("offset", 0.0)
        
        # Determine bounds
        ln, lt = ds["XLONG"].values, ds["XLAT"].values
        if ln.ndim == 3: ln, lt = ln[0], lt[0]
        
        with render_lock:
            # Simple tile rendering logic (Using matplotlib for fast prototyping)
            # In professional production, we'd use a more optimized quadtree approach
            import mercantile
            from PIL import Image
            
            bounds = mercantile.xy_bounds(x, y, z)
            # Create a small 256x256 image
            fig, ax = plt.subplots(figsize=(2.56, 2.56), dpi=100)
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
            ax.set_axis_off()
            
            # Draw the data using pcolormesh on the tile area
            im = ax.pcolormesh(ln, lt, vals, vmin=vmin, vmax=vmax, cmap=colormap, shading='auto')
            
            # Force tile extent
            tile_bounds = mercantile.bounds(x, y, z)
            ax.set_xlim(tile_bounds.west, tile_bounds.east)
            ax.set_ylim(tile_bounds.south, tile_bounds.north)
            
            buf = io.BytesIO()
            fig.savefig(buf, format='png', transparent=True)
            plt.close(fig)
            buf.seek(0)
            
        return send_file(buf, mimetype='image/png')
    except Exception as e:
        app.logger.error(f"Tile error: {e}")
        return str(e), 500

@app.route("/cog_manifest")
def cog_manifest():
    try:
        ds = get_dataset(); ln, lt = ds["XLONG"].values, ds["XLAT"].values
        if ln.ndim == 3: ln, lt = ln[0], lt[0]
        bounds = [float(np.nanmin(ln)), float(np.nanmin(lt)), float(np.nanmax(ln)), float(np.nanmax(lt))]
        manifest = {}
        stem = Path(_CURRENT_FILE["path"]).stem
        for v_id in VARIABLE_CONFIG:
            paths = [f"/cog/{v_id}/{stem}_t{t}.tif" for t in range(ds.sizes.get("Time", 1)) if Path(f"/cog/{v_id}/{stem}_t{t}.tif").exists()]
            if paths: manifest[v_id] = paths
        return jsonify({"variables": manifest, "bounds": bounds})
    except Exception as e: return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
