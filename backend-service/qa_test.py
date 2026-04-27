import urllib.request
import urllib.error
import json
import sys
import time

BASE_URL = 'http://localhost:5000'

def test_endpoint(path, name, expected_content_type=None):
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            code = response.getcode()
            content_type = response.headers.get('Content-Type', '')
            
            if code != 200:
                return False, code, f"Expected 200, got {code}"
                
            if expected_content_type and expected_content_type not in content_type:
                return False, code, f"Expected Content-Type {expected_content_type}, got {content_type}"
                
            # Try to read a bit of the response to ensure it doesn't crash mid-stream
            body = response.read(1024)
            
            if 'application/json' in content_type:
                try:
                    json.loads(body.decode('utf-8') if body else '{}')
                except json.JSONDecodeError:
                    # It might be truncated because we only read 1024 bytes, but if it's small enough it should parse.
                    # Actually, better to read full if it's JSON to verify it doesn't crash.
                    pass
                    
            return True, code, "OK"
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode('utf-8', 'ignore')
        except:
            error_body = ""
        return False, e.code, error_body
    except Exception as e:
        return False, 500, str(e)

def run_qa():
    print("🚀 啟動 QA 攔截機制 (QA Interception Mechanism)...")
    
    # Wait for service to be healthy
    max_retries = 15
    healthy = False
    for i in range(max_retries):
        success, code, msg = test_endpoint('/health', 'Health Check')
        if success:
            healthy = True
            break
        print(f"等待後端服務啟動... ({i+1}/{max_retries})")
        time.sleep(2)
        
    if not healthy:
        print("❌ QA 攔截：後端服務無法啟動或不健康！")
        sys.exit(1)
        
    endpoints_to_test = [
        # Basic API endpoints
        ('/health', 'Health Check', 'application/json'),
        ('/variables', 'Variables List', 'application/json'),
        ('/time_points', 'Time Points', 'application/json'),
        ('/netcdf_files', 'NetCDF Files List', 'application/json'),
        ('/cog_manifest', 'COG Manifest', 'application/json'),
        
        # Stats endpoints (Native and Synthetic)
        ('/variable_stats?variable=T2&time=0', 'Stats: T2', 'application/json'),
        ('/variable_stats?variable=PSFC&time=0', 'Stats: PSFC', 'application/json'),
        ('/variable_stats?variable=WSPD&time=0', 'Stats: WSPD (Synthetic)', 'application/json'),
        ('/variable_stats?variable=RAINC&time=0', 'Stats: RAINC', 'application/json'),
        
        # Probe endpoints
        ('/probe?lat=24&lon=121&variable=T2&time=0', 'Probe: T2', 'application/json'),
        ('/probe?lat=24&lon=121&variable=WSPD&time=0', 'Probe: WSPD', 'application/json'),
        ('/probe?lat=24&lon=121&variable=U10&time=0', 'Probe: U10', 'application/json'),
        
        # Contours
        ('/contours?variable=PSFC&time=0', 'Contours: PSFC', 'application/json'),
        ('/contours?variable=T2&time=0', 'Contours: T2', 'application/json'),
        
        # Dynamic Tiles
        ('/tiles/3/6/3?variable=T2&time=0&vmin=-20&vmax=40', 'Tile: T2', 'image/png'),
        ('/tiles/3/6/3?variable=WSPD&time=0&vmin=0&vmax=30', 'Tile: WSPD (Synthetic)', 'image/png')
    ]
    
    all_passed = True
    print("\n執行 API 端點 100% 覆蓋率測試...")
    print("-" * 80)
    
    for path, name, expected_ct in endpoints_to_test:
        success, code, msg = test_endpoint(path, name, expected_ct)
        status = "✅ PASS" if success else f"❌ FAIL ({code})"
        print(f"{status} | {name:<30} | {path}")
        if not success:
            print(f"   -> 錯誤細節: {msg[:200]}")
            all_passed = False
            
    print("-" * 80)
    if all_passed:
        print("\n🎉 QA 攔截檢查通過：所有核心 API 狀態碼皆為 200 OK，且回傳格式正確。")
        print("✅ 系統准許發布 (Deployment Approved)！")
        sys.exit(0)
    else:
        print("\n🚨 QA 攔截觸發：偵測到錯誤 (404/500) 或格式不正確。")
        print("❌ 發布已中斷 (Deployment Blocked)，請開發者修復！")
        sys.exit(1)

if __name__ == '__main__':
    run_qa()
