import requests
import sys
import json

BASE_URL = "http://localhost:6000"

def log_step(message):
    print(f"[TEST] {message}")

def check_response(response, description, expected_status=200, expected_type=None):
    if response.status_code != expected_status:
        print(f"FAIL: {description} returned {response.status_code} (expected {expected_status})")
        print(f"Response: {response.text[:200]}")
        return False
    
    if expected_type:
        ctype = response.headers.get('Content-Type', '')
        if expected_type not in ctype:
            print(f"FAIL: {description} returned Content-Type '{ctype}' (expected containing '{expected_type}')")
            return False
            
    print(f"PASS: {description}")
    return True

def run_verification():
    print("=== Starting Full Flow Verification ===")
    
    # 0. Ensure GRIB2 file selected (using the logic we added to verify_backend_fix.py)
    # We can just check what is current
    try:
        r = requests.get(f"{BASE_URL}/netcdf_files")
        if r.status_code == 200:
            data = r.json()
            current = data.get('current', '')
            print(f"[INFO] Current file: {current}")
            if not (current.endswith('.grib2') or current.endswith('.grb2')):
                print("[WARN] Current file is NOT GRIB2. Some tests might fail if auto-conversion isn't triggered.")
        else:
            print("[WARN] Could not check current file.")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return False

    # 1. Fetch Time Points
    # Frontend calls /time_points first
    log_step("Fetching time points...")
    try:
        r = requests.get(f"{BASE_URL}/time_points")
        if not check_response(r, "Time Points", 200, "application/json"): return False
        times = r.json()
        if not isinstance(times, list) or len(times) == 0:
            print("FAIL: Time points list is empty or invalid.")
            return False
        print(f"      Found {len(times)} time points. First: {times[0]}")
        first_time = times[0] # Verify using index 0 later
    except Exception as e:
        print(f"FAIL: Exception fetching time points: {e}")
        return False

    # 2. Fetch Variables
    log_step("Fetching variables...")
    try:
        r = requests.get(f"{BASE_URL}/variables")
        if not check_response(r, "Variables", 200, "application/json"): return False
        vars_res = r.json()
        if not isinstance(vars_res, list) or len(vars_res) == 0:
            print("FAIL: Variables list is empty.")
            return False
        print(f"      Found {len(vars_res)} variables: {[v['id'] for v in vars_res]}")
    except Exception as e:
        print(f"FAIL: Exception fetching variables: {e}")
        return False

    # 3. Fetch Wind Metadata (The Fix verification)
    log_step("Fetching Wind Metadata (time=0)...")
    try:
        r = requests.get(f"{BASE_URL}/wind_texture", params={"time": 0, "metadata": "true"})
        if not check_response(r, "Wind Metadata", 200, "application/json"): return False
        meta = r.json()
        required_keys = ['uMin', 'uMax', 'vMin', 'vMax', 'bounds', 'width', 'height']
        missing = [k for k in required_keys if k not in meta]
        if missing:
            print(f"FAIL: Wind metadata missing keys: {missing}")
            return False
        print(f"      Metadata: {json.dumps(meta, indent=2)}")
    except Exception as e:
        print(f"FAIL: Exception fetching wind metadata: {e}")
        return False

    # 4. Fetch Wind Image
    log_step("Fetching Wind Texture Image (time=0)...")
    try:
        r = requests.get(f"{BASE_URL}/wind_texture", params={"time": 0})
        if not check_response(r, "Wind Texture Image", 200, "image/png"): return False
        print(f"      Image size: {len(r.content)} bytes")
    except Exception as e:
        print(f"FAIL: Exception fetching wind image: {e}")
        return False

    # 4.5. Fetch Coords Texture [NEW CHECK]
    log_step("Fetching Coords Texture (time=0)...")
    try:
        r = requests.get(f"{BASE_URL}/coords_texture", params={"time": 0})
        if not check_response(r, "Coords Texture", 200, "image/png"): return False
        
        # Check headers
        required_headers = ['X-Coords-Lon-Range', 'X-Coords-Lat-Range']
        missing = [h for h in required_headers if h not in r.headers]
        if missing:
             print(f"FAIL: Missing headers in coords texture: {missing}")
             return False
        
        print(f"      Coords Image size: {len(r.content)} bytes")
        print(f"      Lon Range: {r.headers['X-Coords-Lon-Range']}")
        print(f"      Lat Range: {r.headers['X-Coords-Lat-Range']}")

    except Exception as e:
        print(f"FAIL: Exception fetching coords texture: {e}")
        return False

    # 5. Fetch Variable Stats (e.g., PSFC)
    log_step("Fetching PSFC stats (time=0)...")
    try:
        r = requests.get(f"{BASE_URL}/variable_stats", params={"variable": "PSFC", "time": 0})
        if not check_response(r, "PSFC Stats", 200, "application/json"): return False
        stats = r.json()
        print(f"      Stats: {json.dumps(stats)}")
        if 'valueRange' not in stats or 'bounds' not in stats:
             print("FAIL: Missing valueRange or bounds in stats.")
             return False
    except Exception as e:
        print(f"FAIL: Exception fetching stats: {e}")
        return False

    print("=== Full Flow Verification PASSED ===")
    return True

if __name__ == "__main__":
    if not run_verification():
        sys.exit(1)
