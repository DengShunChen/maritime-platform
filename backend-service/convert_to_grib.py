import os
import subprocess
import logging
import xarray as xr
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_to_grib2(input_nc_path, output_grib_path=None):
    """
    Convert a NetCDF file to GRIB2 using CDO, handling non-standard WRF grids.
    """
    if not os.path.exists(input_nc_path):
        logger.error(f"Input file not found: {input_nc_path}")
        return False

    if output_grib_path is None:
        output_grib_path = os.path.splitext(input_nc_path)[0] + ".grib2"

    logger.info(f"Converting {input_nc_path} to {output_grib_path}...")

    try:
        # 1. Read coordinates from NetCDF to define the Source Grid (Curvilinear)
        ds = xr.open_dataset(input_nc_path)
        
        # Check available variables
        vars_in_file = list(ds.variables.keys())
        
        # Select pressure variable
        pressure_var = 'PSFC'
        if 'MSLP' in vars_in_file: pressure_var = 'MSLP'
        elif 'SLP' in vars_in_file: pressure_var = 'SLP'
        
        # Select vars to keep
        vars_to_convert = ['T2', 'U10', 'V10', pressure_var]
        # Filter existing only
        vars_to_sel = [v for v in vars_to_convert if v in vars_in_file]
        
        logger.info(f"Variables to convert: {vars_to_sel}")

        # Get coordinates
        if 'XLAT' not in ds or 'XLONG' not in ds:
             logger.error("XLAT/XLONG not found in file.")
             return False

        # Take first time step for coordinates
        lats = ds['XLAT'].isel(Time=0).values
        lons = ds['XLONG'].isel(Time=0).values
        
        # Get dimensions
        ny, nx = lats.shape
        
        # Create Source Grid Description File (Curvilinear)
        source_grid_file = "grid_curv.txt"
        with open(source_grid_file, "w") as f:
            f.write("gridtype = curvilinear\n")
            f.write(f"gridsize = {nx * ny}\n")
            f.write(f"xsize = {nx}\n")
            f.write(f"ysize = {ny}\n")
            f.write("xvals = " + " ".join(map(str, lons.flatten())) + "\n")
            f.write("yvals = " + " ".join(map(str, lats.flatten())) + "\n")
            
        # 2. Create Target Grid Description File (Regular Lat/Lon)
        # Domain based on input file approximate bounds
        min_lon, max_lon = np.min(lons), np.max(lons)
        min_lat, max_lat = np.min(lats), np.max(lats)
        
        # Round outwards
        min_lon = float(np.floor(min_lon * 10) / 10)
        max_lon = float(np.ceil(max_lon * 10) / 10)
        min_lat = float(np.floor(min_lat * 10) / 10)
        max_lat = float(np.ceil(max_lat * 10) / 10)
        
        res = 0.05 # 0.05 degree resolution (~5km)
        xsize = int((max_lon - min_lon) / res)
        ysize = int((max_lat - min_lat) / res)

        target_grid_file = "grid_target.txt"
        with open(target_grid_file, "w") as f:
            f.write("gridtype = lonlat\n")
            f.write(f"xsize = {xsize}\n")
            f.write(f"ysize = {ysize}\n")
            f.write(f"xfirst = {min_lon}\n")
            f.write(f"xinc = {res}\n")
            f.write(f"yfirst = {min_lat}\n")
            f.write(f"yinc = {res}\n")
            
        logger.info(f"Source grid: {nx}x{ny}. Target grid: {min_lon}-{max_lon}, {min_lat}-{max_lat} ({xsize}x{ysize})")

        # 3. Rename mapping
        # Map WRF names to GRIB2 short names
        # T2 -> 2t (167)
        # U10 -> 10u (165)
        # V10 -> 10v (166)
        # PSFC -> sp (134) or MSLP -> msl (151)
        
        chname_map = f"T2,2t,U10,10u,V10,10v,{pressure_var},sp"
        if pressure_var == 'MSLP' or pressure_var == 'SLP':
             chname_map = chname_map.replace(',sp', ',msl')

        selname_arg = ",".join(vars_to_sel)

        # 4. cleanup old file if exists
        if os.path.exists(output_grib_path):
            os.remove(output_grib_path)

        # 5. Run CDO command
        # Pipeline:
        # 1. Select variables
        # 2. Set grid to curvilinear (using generated file)
        # 3. Remap to target grid
        # 4. Change names
        # 5. Output
        
        # cdo -f grb2 -chname,... -remapbil,target.txt -setgrid,source.txt -selname,... input output
        
        cmd = [
            "cdo", "-f", "grb2",
            f"-chname,{chname_map}",
            f"-remapbil,{target_grid_file}",
            f"-setgrid,{source_grid_file}",
            f"-selname,{selname_arg}",
            input_nc_path,
            output_grib_path
        ]
        
        # logger.info("Running command: " + " ".join(cmd))
        # Note: 'xvals=' line can be huge, causing "Argument list too long" if passed directly in command line?
        # No, we verify file size. grid_curv.txt is created on disk. cdo reads it. 
        # The command line itself is short.
        
        subprocess.run(cmd, check=True)
        
        logger.info(f"Conversion successful: {output_grib_path}")
        return output_grib_path

    except subprocess.CalledProcessError as e:
        logger.error(f"CDO conversion failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None
    finally:
        ds.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert NetCDF to GRIB2 using CDO.")
    parser.add_argument("input_file", help="Path to input NetCDF file")
    parser.add_argument("--output", help="Path to output GRIB2 file", default=None)
    
    args = parser.parse_args()
    convert_to_grib2(args.input_file, args.output)
