import requests
import time
import statistics

BASE_URL = "http://localhost:6000"
ITERATIONS = 5

def benchmark_endpoint(name, url, params=None):
    print(f"Benchmarking {name} ({url})...")
    times = []
    success_count = 0
    
    for i in range(ITERATIONS):
        start = time.time()
        try:
            r = requests.get(url, params=params)
            r.raise_for_status()
            duration = time.time() - start
            times.append(duration)
            success_count += 1
            print(f"  Run {i+1}: {duration:.4f}s")
        except Exception as e:
            print(f"  Run {i+1}: FAILED ({e})")

    if times:
        avg = statistics.mean(times)
        med = statistics.median(times)
        print(f"  Result: Avg={avg:.4f}s, Median={med:.4f}s (Success: {success_count}/{ITERATIONS})")
        return avg
    return -1


def setup_grib2():
    print("Setting up GRIB2 file...")
    try:
        r = requests.get(f"{BASE_URL}/netcdf_files")
        if r.status_code != 200: return False
        data = r.json()
        current = data.get('current', '')
        if current.endswith('.grib2') or current.endswith('.grb2'):
            return True
        grib_files = [f for f in data.get('files', []) if f['filename'].endswith('.grib2')]
        if not grib_files: return False
        target = grib_files[0]['path']
        requests.post(f"{BASE_URL}/netcdf_files/select", json={"path": target})
        return True
    except:
        return False

if __name__ == "__main__":
    if not setup_grib2():
        print("Failed to setup GRIB2")
        exit(1)
        
    print("=== Performance Benchmark ===")
    
    # 1. /wind_texture (Used for wind particles)
    benchmark_endpoint("Wind Texture (PNG)", f"{BASE_URL}/wind_texture", {"time": 0})
    
    # 2. /variable_data (Used for color overlays like Pressure, Temp)
    # This uses matplotlib pcolormesh
    benchmark_endpoint("Variable Data (Plot)", f"{BASE_URL}/variable_data", {"variable": "PSFC", "time": 0})
    
    # 3. /tiles (Used for tiled map layers - scalar fields)
    # Uses griddata interpolation
    benchmark_endpoint("Map Tile (Z=4)", f"{BASE_URL}/tiles/4/13/6", {"variable": "PSFC", "time": 0})
    
    print("=== End Benchmark ===")
