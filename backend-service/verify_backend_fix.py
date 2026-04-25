import requests
import sys

def verify_metadata_endpoint():
    print("Testing /wind_texture?metadata=true (expecting JSON)...")
    url = "http://localhost:6000/wind_texture?time=0&metadata=true"
    try:
        response = requests.get(url)
        # We don't raise_for_status yet because we want to inspect content type first
        
        ctype = response.headers.get('Content-Type')
        print(f"  Content-Type: {ctype}")
        
        if ctype != 'application/json':
            print(f"FAIL: Expected 'application/json', got '{ctype}'")
            return False
            
        data = response.json()
        print("  JSON decoded successfully.")
        
        expected_keys = ['uMin', 'uMax', 'vMin', 'vMax', 'bounds', 'width', 'height']
        missing = [k for k in expected_keys if k not in data]
        
        if missing:
            print(f"FAIL: Missing keys in JSON: {missing}")
            return False
            
        print("PASS: Metadata JSON valid.")
        return True
        
    except Exception as e:
        print(f"FAIL: Request error: {e}")
        return False

def verify_png_endpoint():
    print("Testing /wind_texture (expecting PNG)...")
    url = "http://localhost:6000/wind_texture?time=0"
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        ctype = response.headers.get('Content-Type')
        print(f"  Content-Type: {ctype}")
        
        if ctype != 'image/png':
            print(f"FAIL: Expected 'image/png', got '{ctype}'")
            return False
            
        print("PASS: Texture PNG valid.")
        return True
        
    except Exception as e:
        print(f"FAIL: Request error: {e}")
        return False

def setup_grib2_file():
    print("Setting up GRIB2 file...")
    base_url = "http://localhost:6000"
    
    # List files to find a valid GRIB2
    try:
        r = requests.get(f"{base_url}/netcdf_files")
        r.raise_for_status()
        data = r.json()
        current = data.get('current', '')
        print(f"  Current file: {current}")
        
        if current.endswith('.grib2') or current.endswith('.grb2'):
            print("  Current file is already GRIB2.")
            return True
            
        # Find a grib2 file
        grib_files = [f for f in data.get('files', []) if f['filename'].endswith('.grib2')]
        if not grib_files:
            print("FAIL: No GRIB2 files found in /netcdf_files list.")
            return False
            
        target = grib_files[0]
        target_path = target['path'] # usually full path or relative?
        # app.py list_netcdf_files uses os.path.join(data_dir, filename) for 'path'.
        # But select_netcdf_file expects 'path' from request.
        
        print(f"  Selecting: {target_path}")
        
        r = requests.post(f"{base_url}/netcdf_files/select", json={"path": target_path})
        r.raise_for_status()
        print("  Selection successful.")
        return True
        
    except Exception as e:
        print(f"FAIL: Setup error: {e}")
        return False

if __name__ == "__main__":
    if not setup_grib2_file():
        sys.exit(1)
        
    success = True
    success &= verify_metadata_endpoint()
    print("-" * 20)
    success &= verify_png_endpoint()
    
    if not success:
        sys.exit(1)
