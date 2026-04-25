import xarray as xr
import os
import sys

def verify_grib(path):
    print(f"Verifying GRIB2 file: {path}")
    if not os.path.exists(path):
        print("File not found.")
        sys.exit(1)

    try:
        # Open with cfgrib
        ds = xr.open_dataset(path, engine="cfgrib") #, backend_kwargs={'indexpath': ''})
        print("Successfully opened with xarray/cfgrib.")
        print("Variables found:")
        for var in ds.data_vars:
            print(f" - {var}: {ds[var].dims}, {ds[var].shape}")
            print(f"   attrs: {ds[var].attrs}")
        
        # Check specific expected vars
        expected = ['sp', '2t', '10u', '10v']
        found = [v for v in expected if v in ds]
        print(f"Found expected variables: {found}")
        
    except Exception as e:
        print(f"Error opening GRIB2: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to GRIB2 file")
    args = parser.parse_args()
    verify_grib(args.path)
