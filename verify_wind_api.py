import requests
import json
import sys

def test_wind_api():
    url = "http://localhost:6000/wind_data?time=0"
    print(f"Testing {url}...")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        
        # Check top-level keys
        required_keys = ['points', 'bounds', 'count']
        for key in required_keys:
            if key not in data:
                print(f"FAIL: Missing key '{key}' in response")
                sys.exit(1)
                
        # Check points
        points = data['points']
        count = data['count']
        
        if len(points) != count:
            print(f"FAIL: Count mismatch. Claimed {count}, got {len(points)}")
            sys.exit(1)
            
        print(f"Received {count} wind vectors.")
        
        if count == 0:
            print("WARNING: No points returned. Is the data empty?")
        else:
            # Check first point structure
            p0 = points[0]
            if not all(k in p0 for k in ['lon', 'lat', 'u', 'v']):
                print(f"FAIL: Invalid point structure: {p0}")
                sys.exit(1)
            
            print(f"Sample point: {p0}")
            
            # Analyze Latitude Ordering
            lats = [p['lat'] for p in points]
            print(f"Lat Range: Min={min(lats):.4f}, Max={max(lats):.4f}")
            print(f"Lat[0]={lats[0]:.4f}, Lat[-1]={lats[-1]:.4f}")
            
            # Check for general trend (assuming row-major order)
            # Compare first block vs last block
            if lats[0] < lats[-1]:
                print("ORDER: South to North (Ascending)")
                print("CONCLUSION: V=0 is Bottom (South). +V moves UP (North). Matches shader.")
            else:
                print("ORDER: North to South (Descending)")
                print("CONCLUSION: V=0 is Top (North). +V moves DOWN (North). SHADER INVERTED?")
                
            print("PASS: API structure valid.")
            
    except Exception as e:
        print(f"FAIL: Request error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_wind_api()
