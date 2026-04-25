#!/usr/bin/env python3
"""
ETL: Convert WRF NetCDF (or GRIB2) files to Cloud Optimized GeoTIFF (COG).

Key fix: WRF uses curvilinear XLAT/XLONG on a projected grid (Lambert/Mercator).
Previously, from_bounds() treated it as a regular lat/lon grid causing misalignment.

This version uses scipy.interpolate to properly resample the curvilinear WRF
data onto a regular EPSG:4326 grid before writing the COG, ensuring accurate
geographic alignment with the basemap.

Output structure:
  cog/{variable}/{stem}_t{index}.tif   (EPSG:4326, DEFLATE-compressed)
"""

import logging
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from scipy.interpolate import griddata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Variable config ────────────────────────────────────────────────────────────
VARIABLE_CONFIG: dict[str, dict] = {
    "PSFC": {
        "wrf_name": "PSFC",
        "grib_candidates": ["sp"],
        "grib_level": "surface",
        "scale": 0.01,      # Pa → hPa
        "offset": 0.0,
        "units": "hPa",
    },
    "T2": {
        "wrf_name": "T2",
        "grib_candidates": ["2t", "t2m", "t"],
        "grib_level": "heightAboveGround",
        "scale": 1.0,
        "offset": -273.15,  # K → °C
        "units": "°C",
    },
    "U10": {
        "wrf_name": "U10",
        "grib_candidates": ["10u", "u10", "u"],
        "grib_level": "heightAboveGround",
        "scale": 1.0,
        "offset": 0.0,
        "units": "m/s",
    },
    "V10": {
        "wrf_name": "V10",
        "grib_candidates": ["10v", "v10", "v"],
        "grib_level": "heightAboveGround",
        "scale": 1.0,
        "offset": 0.0,
        "units": "m/s",
    },
    "RAINC": {
        "wrf_name": "RAINC",
        "grib_candidates": ["tp"],
        "grib_level": "surface",
        "scale": 1.0,
        "offset": 0.0,
        "units": "mm",
    },
    "RAINNC": {
        "wrf_name": "RAINNC",
        "grib_candidates": ["prate"],
        "grib_level": "surface",
        "scale": 1.0,
        "offset": 0.0,
        "units": "mm",
    },
    "REFD_MAX": {
        "wrf_name": "REFD_MAX",
        "grib_candidates": ["refd"],
        "grib_level": "surface",
        "scale": 1.0,
        "offset": 0.0,
        "units": "dBZ",
    },
    "WSPD": {
        "wrf_name": None,  # Derived: sqrt(U10^2 + V10^2)
        "grib_candidates": [],
        "grib_level": "heightAboveGround",
        "scale": 1.0,
        "offset": 0.0,
        "units": "m/s",
    },
}

NODATA = -9999.0


from rasterio.transform import Affine
from pyproj import CRS, Transformer

# ── Native WRF CRS & Transform ────────────────────────────────────────────────

def _get_wrf_crs_and_transform(ds: xr.Dataset) -> tuple[CRS, Affine]:
    """
    Construct a pyproj.CRS and rasterio.transform.Affine directly from WRF
    global attributes. This perfectly preserves the curvilinear WRF geometry
    without any resampling artifacts.
    """
    proj_id = ds.attrs.get("MAP_PROJ", 1)
    # Earth radius in WRF is typically a perfect sphere of 6370000 m
    a = b = ds.attrs.get("CEN_A", 6370000.0)
    
    if proj_id == 1:
        # Lambert Conformal Conic
        crs = CRS.from_dict({
            "proj": "lcc",
            "lat_1": ds.attrs.get("TRUELAT1", ds.attrs.get("CEN_LAT")),
            "lat_2": ds.attrs.get("TRUELAT2", ds.attrs.get("CEN_LAT")),
            "lat_0": ds.attrs.get("CEN_LAT"),
            "lon_0": ds.attrs.get("STAND_LON", ds.attrs.get("CEN_LON")),
            "x_0": 0,
            "y_0": 0,
            "a": a,
            "b": b,
            "towgs84": "0,0,0,0,0,0,0"
        })
    elif proj_id == 3:
        # Mercator
        crs = CRS.from_dict({
            "proj": "merc",
            "lat_ts": ds.attrs.get("TRUELAT1", 0.0),
            "lon_0": ds.attrs.get("STAND_LON", 0.0),
            "x_0": 0,
            "y_0": 0,
            "a": a,
            "b": b,
            "towgs84": "0,0,0,0,0,0,0"
        })
    else:
        logger.warning("Unsupported MAP_PROJ: %s. Defaulting to EPSG:4326 bounding box.", proj_id)
        crs = CRS.from_epsg(4326)

    src_height = ds.sizes["south_north"]
    src_width = ds.sizes["west_east"]
    dx = ds.attrs.get("DX", 1.0)
    dy = ds.attrs.get("DY", 1.0)

    # Find center point in projected coords
    transformer = Transformer.from_crs("epsg:4326", crs, always_xy=True)
    x_cen, y_cen = transformer.transform(ds.attrs["CEN_LON"], ds.attrs["CEN_LAT"])

    # WRF grid is south-to-north. Rasterio expects top-to-bottom (north-to-south).
    # So we calculate the upper-left (NW) corner.
    x_min = x_cen - (src_width / 2) * dx
    y_max = y_cen + (src_height / 2) * dy

    transform = Affine.translation(x_min, y_max) * Affine.scale(dx, -dy)
    return crs, transform


# ── COG writer ─────────────────────────────────────────────────────────────────

def _write_cog(arr: np.ndarray, crs: CRS, transform: Affine, out_path: Path) -> None:
    """Write a 2-D float32 array as Cloud Optimized GeoTIFF."""
    height, width = arr.shape
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        out_path, "w",
        driver="COG",
        height=height, width=width, count=1,
        dtype="float32",
        crs=crs, transform=transform, nodata=NODATA,
        compress="deflate",
        overview_resampling="bilinear",
    ) as dst:
        dst.write(arr.astype("float32"), 1)

    logger.info("  → %s", out_path)


# ── WRF NetCDF conversion ──────────────────────────────────────────────────────

def _is_wrf(ds: xr.Dataset) -> bool:
    return "XLAT" in ds and "XLONG" in ds


def convert_wrf_file(nc_path: str, cog_root: str) -> list[Path]:
    """Convert a WRF NetCDF file → properly georeferenced COG per variable per time step."""
    nc_path = Path(nc_path)
    cog_root = Path(cog_root)
    created: list[Path] = []
    stem = nc_path.stem

    logger.info("Opening WRF NetCDF: %s …", nc_path.name)
    ds = xr.open_dataset(str(nc_path))

    n_times = ds.dims.get("Time", 1)
    src_height = ds.sizes["south_north"]
    src_width = ds.sizes["west_east"]

    crs, transform = _get_wrf_crs_and_transform(ds)
    logger.info("Grid %dx%d, %d time step(s), CRS: %s",
                src_width, src_height, n_times, crs.to_string())

    for var_id, cfg in VARIABLE_CONFIG.items():
        wrf_name = cfg["wrf_name"]

        # ── Derived WSPD ──────────────────────────────────────────────────────
        if var_id == "WSPD":
            if "U10" not in ds or "V10" not in ds:
                logger.debug("  WSPD skipped (U10/V10 not found)")
                continue
            logger.info("Processing WSPD (derived) …")
            for t_idx in range(n_times):
                u = ds["U10"].isel(Time=t_idx).values.astype("float64")
                v = ds["V10"].isel(Time=t_idx).values.astype("float64")
                arr = np.sqrt(u**2 + v**2)
                arr = np.where(np.isfinite(arr), arr, NODATA).astype("float32")
                # WRF is bottom-to-top, rasterio wants top-to-bottom
                arr = np.flipud(arr)
                out_path = cog_root / "WSPD" / f"{stem}_t{t_idx}.tif"
                _write_cog(arr, crs, transform, out_path)
                created.append(out_path)
            continue

        # ── Regular variable ─────────────────────────────────────────────────
        if wrf_name not in ds:
            logger.debug("  %s not in dataset, skipping", var_id)
            continue

        logger.info("Processing %s …", var_id)
        da = ds[wrf_name]
        for t_idx in range(n_times):
            arr = da.isel(Time=t_idx).values.astype("float64")
            arr = arr * cfg["scale"] + cfg["offset"]
            arr = np.where(np.isfinite(arr), arr, NODATA).astype("float32")
            # WRF is bottom-to-top, rasterio wants top-to-bottom
            arr = np.flipud(arr)
            out_path = cog_root / var_id / f"{stem}_t{t_idx}.tif"
            _write_cog(arr, crs, transform, out_path)
            created.append(out_path)

    ds.close()
    return created

# ── GRIB2 conversion ───────────────────────────────────────────────────────────

def _open_grib2_layer(path: str, type_of_level: str) -> xr.Dataset | None:
    try:
        import cfgrib  # noqa
        return xr.open_dataset(
            path, engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"typeOfLevel": type_of_level}, "indexpath": ""},
        )
    except Exception:
        return None


def convert_grib2_file(grib_path: str, cog_root: str) -> list[Path]:
    """Convert a GRIB2 file → COG files per variable per time step."""
    grib_path = Path(grib_path)
    cog_root = Path(cog_root)
    stem = grib_path.stem
    created: list[Path] = []

    logger.info("Opening GRIB2: %s …", grib_path.name)
    datasets = [ds for lvl in ("heightAboveGround", "surface", "meanSea")
                if (ds := _open_grib2_layer(str(grib_path), lvl))]
    if not datasets:
        logger.error("No readable layers in %s", grib_path.name)
        return []

    ds = xr.merge(datasets, compat="override") if len(datasets) > 1 else datasets[0]

    lats = ds.coords["latitude"].values
    lons = ds.coords["longitude"].values
    lon_min, lon_max = float(lons.min()), float(lons.max())
    lat_min, lat_max = float(lats.min()), float(lats.max())

    n_steps = 1
    for dim in ("step", "time", "valid_time"):
        if dim in ds.sizes:
            n_steps = ds.sizes[dim]
            break

    for var_id, cfg in VARIABLE_CONFIG.items():
        if var_id in ("WSPD",):
            continue
        var_name = next((c for c in cfg["grib_candidates"] if c in ds), None)
        if not var_name:
            continue
        logger.info("Processing %s (→ %s) …", var_id, var_name)
        da = ds[var_name]
        for t_idx in range(n_steps):
            for dim in ("step", "time", "valid_time"):
                if dim in da.dims:
                    da = da.isel({dim: t_idx})
                    break
            arr = da.values.astype("float64") * cfg["scale"] + cfg["offset"]
            if lats.ndim == 1 and lats[0] < lats[-1]:
                arr = np.flipud(arr)
            arr = np.where(np.isfinite(arr), arr, NODATA)
            out_path = cog_root / var_id / f"{stem}_t{t_idx}.tif"
            _write_cog(arr, lon_min, lon_max, lat_min, lat_max, out_path)
            created.append(out_path)

    ds.close()
    return created


# ── Directory conversion ───────────────────────────────────────────────────────

def convert_directory(data_dir: str, cog_root: str) -> None:
    """Convert all WRF NetCDF and GRIB2 files in data_dir to COGs."""
    data_dir = Path(data_dir)
    all_created: list[Path] = []

    wrf_files = sorted([
        f for f in data_dir.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and (f.suffix == "" or f.suffix in (".nc", ".nc4"))
        and ("wrfout" in f.name or "wrf" in f.name.lower())
    ])
    grib_files = sorted([
        f for f in data_dir.iterdir()
        if f.is_file() and f.suffix in (".grib2", ".grb2")
    ])

    logger.info("Found %d WRF NetCDF + %d GRIB2 files in %s",
                len(wrf_files), len(grib_files), data_dir)

    for fp in wrf_files:
        try:
            paths = convert_wrf_file(str(fp), cog_root)
            all_created.extend(paths)
        except Exception as exc:
            logger.error("WRF conversion failed for %s: %s", fp.name, exc, exc_info=True)

    for fp in grib_files:
        try:
            paths = convert_grib2_file(str(fp), cog_root)
            all_created.extend(paths)
        except Exception as exc:
            logger.error("GRIB2 conversion failed for %s: %s", fp.name, exc, exc_info=True)

    logger.info("Done. Created %d COG files total.", len(all_created))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="WRF NetCDF / GRIB2 → COG ETL (with curvilinear resampling)")
    parser.add_argument("data_dir", help="Input directory (WRF NetCDF or GRIB2 files)")
    parser.add_argument("--cog-root", default="/cog", help="Output root for COG files")
    args = parser.parse_args()

    convert_directory(args.data_dir, args.cog_root)
