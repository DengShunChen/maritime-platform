import requests
from PIL import Image
import io

def test_endpoint(name, url):
    print(f"\n--- Testing {name} ---")
    print(f"URL: {url}")
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        
        if response.status_code == 200:
            if 'image' in response.headers.get('Content-Type', ''):
                print(f"Content Length: {len(response.content)}")
                try:
                    img = Image.open(io.BytesIO(response.content))
                    img.verify()
                    print("Image is valid.")
                    print(f"Format: {img.format}, Size: {img.size}, Mode: {img.mode}")
                except Exception as e:
                    print(f"Error opening image: {e}")
            else:
                print("Response is not an image.")
                print(f"Content: {response.text[:200]}...") # Print first 200 chars
        else:
            print(f"Response not 200: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

# 1. Test Variables List
test_endpoint("Variables List", 'http://localhost:6000/variables')

# 2. Test Legacy Endpoint (SLP)
test_endpoint("Legacy SLP", 'http://localhost:6000/slp_data?time=0')

# 3. Test New Endpoint - Temperature
test_endpoint("New Variable (T2)", 'http://localhost:6000/variable_data?time=0&variable=T2')

# 4. Test New Endpoint - Wind (U10)
test_endpoint("New Variable (U10)", 'http://localhost:6000/variable_data?time=0&variable=U10')
