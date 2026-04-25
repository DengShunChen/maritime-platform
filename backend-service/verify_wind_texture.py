import requests
import sys

def verify_endpoint(name, url):
    print(f"Testing {name} ({url})...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # Check Content-Type
        ctype = response.headers.get('Content-Type')
        if ctype != 'image/png':
            print(f"FAIL: Expected 'image/png', got '{ctype}'")
            return False
            
        print(f"  Status: {response.status_code}")
        print(f"  Content-Type: {ctype}")
        print(f"  Size: {len(response.content)} bytes")
        
        # Check Headers
        headers_to_check = []
        if name == 'wind_texture':
            headers_to_check = ['X-Wind-U-Range', 'X-Wind-V-Range', 'X-Wind-Bounds', 'X-Wind-Grid-Size']
        elif name == 'coords_texture':
            headers_to_check = ['X-Coords-Lon-Range', 'X-Coords-Lat-Range', 'X-Coords-Grid-Size']
            
        all_headers_ok = True
        for h in headers_to_check:
            val = response.headers.get(h)
            if val:
                print(f"  {h}: {val}")
            else:
                print(f"FAIL: Missing header '{h}'")
                all_headers_ok = False
        
        if not all_headers_ok:
            return False
            
        print(f"PASS: {name} valid.")
        return True
        
    except Exception as e:
        print(f"FAIL: Request error: {e}")
        return False

def main():
    base_url = "http://localhost:6000"
    
    success = True
    success &= verify_endpoint('wind_texture', f"{base_url}/wind_texture?time=0")
    print("-" * 20)
    success &= verify_endpoint('coords_texture', f"{base_url}/coords_texture?time=0")
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
