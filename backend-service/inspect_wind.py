
import xarray as xr
import numpy as np
import os

# Path to data
# Using the path from app.py
NETCDF_PATH = "data/wrfout_d01_2025-09-18_00:00:00"

def inspect_wind():
    if not os.path.exists(NETCDF_PATH):
        print(f"File not found: {NETCDF_PATH}")
        return

    try:
        ds = xr.open_dataset(NETCDF_PATH, engine="netcdf4")
        print("Dataset opened successfully.")
        
        # Check variables
        if 'U10' not in ds or 'V10' not in ds:
            print("U10 or V10 not found.")
            return

        # Get first time step
        u = ds['U10'].isel(Time=0).values
        v = ds['V10'].isel(Time=0).values
        
        print(f"U10 shape: {u.shape}")
        print(f"V10 shape: {v.shape}")
        
        # Calculate WSPD
        wspd = np.sqrt(u**2 + v**2)
        
        print("\n--- Statistics (Time=0) ---")
        print(f"U10:  Min={np.nanmin(u):.3f}, Max={np.nanmax(u):.3f}, Mean={np.nanmean(u):.3f}")
        print(f"V10:  Min={np.nanmin(v):.3f}, Max={np.nanmax(v):.3f}, Mean={np.nanmean(v):.3f}")
        print(f"WSPD: Min={np.nanmin(wspd):.3f}, Max={np.nanmax(wspd):.3f}, Mean={np.nanmean(wspd):.3f}")
        
        # Check for outliers
        outliers = wspd[wspd > 100]
        print(f"\nWSPD > 100 m/s count: {len(outliers)}")
        if len(outliers) > 0:
            print(f"Top 5 outliers: {np.sort(outliers)[-5:]}")

        # Check for NaNs
        print(f"NaN count in WSPD: {np.isnan(wspd).sum()}")
        
        ds.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_wind()
