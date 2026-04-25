import xarray as xr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from geoalchemy2 import WKTElement
import os
import numpy as np
from datetime import datetime, timedelta
from models import Base, TimePoint, SpatialGrid, SlpData

# Database connection string
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/maritime_db")

def import_data_to_db(file_path="wrfout_v2_Lambert.grib2", clear_tables=True):
    engine = create_engine(DATABASE_URL)
    conn = engine.connect()
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
    conn.commit()
    conn.close()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if clear_tables:
            session.execute(text("TRUNCATE TABLE slp_data RESTART IDENTITY CASCADE;"))
            session.execute(text("TRUNCATE TABLE time_points RESTART IDENTITY CASCADE;"))
            session.execute(text("TRUNCATE TABLE spatial_grid RESTART IDENTITY CASCADE;"))
            session.commit()
            print("Cleared existing data.")

        print(f"Loading file: {file_path}...")
        
        is_grib = file_path.endswith('.grib2') or file_path.endswith('.grb2')
        
        if is_grib:
            # GRIB2 usually separates T2 (Height) and PSFC (Surface). 
            # We need Surface/MeanSea for Pressure.
            try:
                # Try loading Surface fields (sp) or Mean Sea Level (msl)
                ds = xr.open_dataset(file_path, engine="cfgrib", 
                                     backend_kwargs={'filter_by_keys': {'typeOfLevel': 'surface'}, 'indexpath': ''})
                if 'sp' not in ds:
                     ds.close()
                     ds = xr.open_dataset(file_path, engine="cfgrib", 
                                          backend_kwargs={'filter_by_keys': {'typeOfLevel': 'meanSea'}, 'indexpath': ''})
            except Exception:
                # Fallback to generic open
                ds = xr.open_dataset(file_path, engine="cfgrib", backend_kwargs={'indexpath': ''})
        else:
            ds = xr.open_dataset(file_path)

        print("File loaded.")
        print(f"Variables: {list(ds.variables.keys())}")

        # Variable Selection
        pressure_var = None
        if 'sp' in ds: pressure_var = 'sp'
        elif 'msl' in ds: pressure_var = 'msl'
        elif 'PSFC' in ds: pressure_var = 'PSFC'
        
        if not pressure_var:
            raise ValueError("No pressure variable (sp, msl, PSFC) found.")
        
        print(f"Pressure variable: {pressure_var}")

        # --- Time Points ---
        print("Importing time points...")
        time_stamps = []
        
        if 'time' in ds.coords and 'step' in ds.coords:
            # GRIB style: time + step
            # Note: valid_time often exists as a coord which is the absolute time
            if 'valid_time' in ds.coords:
                vt = ds['valid_time'].values
                # Ensure iterable
                if vt.ndim == 0: vt = [vt]
                
                for t in vt:
                    # numpy datetime64 to timestamp
                    ts = (t - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 's')
                    time_stamps.append(int(ts))
            else:
                 # Fallback
                 base_time = ds['time'].values
                 steps = ds['step'].values
                 if steps.ndim == 0: steps = [steps]
                 
                 base_ts = (base_time - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 's')
                 for s in steps:
                     # step is usually nanoseconds in xarray? or timedelta64
                     s_sec = s / np.timedelta64(1, 's')
                     time_stamps.append(int(base_ts + s_sec))
                     
        elif 'Times' in ds:
             # WRF NetCDF style
            times_raw = ds['Times'].values
            for t in times_raw:
                if isinstance(t, bytes): time_str = t.decode('utf-8')
                else: time_str = str(t)
                time_str = time_str.strip().replace('_', 'T')
                dt = datetime.fromisoformat(time_str)
                time_stamps.append(int(dt.timestamp()))
        else:
            # Simple Time dimension
             if 'time' in ds.coords:
                times = ds['time'].values
                if times.ndim == 0: times = [times]
                for t in times:
                    ts = (t - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 's')
                    time_stamps.append(int(ts))

        time_point_map = {}
        for i, ts_val in enumerate(time_stamps):
            # Upsert or ignore? For now simple insert
            # Check exist?
            tp = session.query(TimePoint).filter_by(timestamp=ts_val).first()
            if not tp:
                tp = TimePoint(timestamp=ts_val)
                session.add(tp)
                session.flush()
            time_point_map[i] = tp.id
        session.commit()
        print(f"Time points: {len(time_point_map)}")

        # --- Spatial Grid ---
        print("Importing spatial grid...")
        
        # Detect 1D (GRIB) or 2D (NetCDF) coords
        lats = ds.coords['latitude'].values if 'latitude' in ds.coords else ds['XLAT'].isel(Time=0).values
        lons = ds.coords['longitude'].values if 'longitude' in ds.coords else ds['XLONG'].isel(Time=0).values
        
        if lats.ndim == 1 and lons.ndim == 1:
            # Meshgrid for GRIB 1D
            lons_2d, lats_2d = np.meshgrid(lons, lats)
        else:
            lons_2d, lats_2d = lons, lats
            
        flat_lons = lons_2d.flatten()
        flat_lats = lats_2d.flatten()
        
        print(f"Grid size: {len(flat_lons)}")
        
        # Batch insert grid
        # To optimize, we should only insert NEW points.
        # But `spatial_grid` map logic requires knowing IDs.
        # For this script, we TRUNCATED tables if clear_tables=True, so just bulk insert.
        
        grid_points_buffer = []
        spatial_grid_map = {} # (lon, lat) -> id
        
        # Pre-assign IDs to avoid round-trip? No, let DB assign. Use COPY for speed? 
        # For simplicity in python:
        
        for i in range(len(flat_lons)):
            lon = float(flat_lons[i])
            lat = float(flat_lats[i])
            
            # Simple optimization: GRIB grid is regular, distinct?
            # Yes.
            
            wkt = f'POINT({lon} {lat})'
            grid_points_buffer.append({'longitude': lon, 'latitude': lat, 'geom': wkt})
            
        # Bulk insert using Core
        # Chunking
        chunk_size = 5000
        for i in range(0, len(grid_points_buffer), chunk_size):
            chunk = grid_points_buffer[i:i+chunk_size]
            # Use raw SQL or bulk_save_objects? 
            # bulk_save_objects with return_defaults is slow.
            # Let's use INSERT ... RETURNING id
            # actually we need the IDs mapped back. 
            
            # Slow path: add objects
            objs = [SpatialGrid(longitude=p['longitude'], latitude=p['latitude'], geom=WKTElement(p['geom'], srid=4326)) for p in chunk]
            session.add_all(objs)
            session.flush() # Get IDs
            
            for obj in objs:
                spatial_grid_map[(float(obj.longitude), float(obj.latitude))] = obj.id
                
            session.commit()
            if i % 10000 == 0: print(f"Grid progress: {i}/{len(grid_points_buffer)}")
            
        print("Grid imported.")

        # --- Data ---
        print("Importing Data...")
        # Get data values
        # Shape: (time, y, x) or (time, LAT, LON)
        vals = ds[pressure_var].values
        
        # If shape matches flat grid directly?
        # Vals shape: (T, Y, X). Flat grid is Y*X.
        
        for t_i in range(len(time_stamps)):
            t_id = time_point_map[t_i]
            
            # Slicing
            # Handle possible extra dims like step/surface if not filtered?
            # We filtered open_dataset.
            
            # If GRIB, vals[t_i] is (Y, X)
            vals_slice = vals[t_i].flatten()
            
            data_objs = []
            for g_i in range(len(flat_lons)):
                val = float(vals_slice[g_i])
                lon = float(flat_lons[g_i])
                lat = float(flat_lats[g_i])
                
                g_id = spatial_grid_map.get((lon, lat))
                if g_id:
                     data_objs.append(SlpData(time_id=t_id, grid_id=g_id, pressure_value=val))
            
            # Bulk add
            for i in range(0, len(data_objs), 5000):
                session.add_all(data_objs[i:i+5000])
                session.commit()
                
            print(f"Time step {t_i} imported.")

        print("Done.")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('file', nargs='?', default="wrfout_v2_Lambert.grib2")
    parser.add_argument('--no-clear', action='store_false', dest='clear_tables', default=True)
    args = parser.parse_args()
    
    import_data_to_db(args.file, args.clear_tables)