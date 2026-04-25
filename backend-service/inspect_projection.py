import xarray as xr
import numpy as np

NETCDF_PATH = "data/wrfout_d01_2025-09-18_00:00:00"

ds = xr.open_dataset(NETCDF_PATH, engine="netcdf4")

print("=== NetCDF 投影屬性 ===")
print(f"MAP_PROJ: {ds.attrs.get('MAP_PROJ', 'N/A')} (1=Lambert CC, 2=Polar, 3=Mercator)")
print(f"TRUELAT1: {ds.attrs.get('TRUELAT1', 'N/A')}")
print(f"TRUELAT2: {ds.attrs.get('TRUELAT2', 'N/A')}")
print(f"STAND_LON: {ds.attrs.get('STAND_LON', 'N/A')}")
print(f"CEN_LAT: {ds.attrs.get('CEN_LAT', 'N/A')}")
print(f"CEN_LON: {ds.attrs.get('CEN_LON', 'N/A')}")
print(f"DX: {ds.attrs.get('DX', 'N/A')} m")
print(f"DY: {ds.attrs.get('DY', 'N/A')} m")

print("\n=== XLAT/XLONG 坐標 (WGS84 經緯度) ===")
xlat = ds['XLAT'].isel(Time=0).values
xlong = ds['XLONG'].isel(Time=0).values
print(f"Grid shape: {xlat.shape}")
print(f"XLAT range: [{xlat.min():.4f}, {xlat.max():.4f}]")
print(f"XLONG range: [{xlong.min():.4f}, {xlong.max():.4f}]")

print("\n=== 四個角落坐標 ===")
print(f"左下 (BL): lat={xlat[0, 0]:.4f}, lon={xlong[0, 0]:.4f}")
print(f"右下 (BR): lat={xlat[0, -1]:.4f}, lon={xlong[0, -1]:.4f}")
print(f"左上 (TL): lat={xlat[-1, 0]:.4f}, lon={xlong[-1, 0]:.4f}")
print(f"右上 (TR): lat={xlat[-1, -1]:.4f}, lon={xlong[-1, -1]:.4f}")

print("\n=== 網格是否為曲線網格 ===")
# 在正規網格中，同一行的緯度應該相同
lat_row_variation = xlat[0, :].max() - xlat[0, :].min()
lon_col_variation = xlong[:, 0].max() - xlong[:, 0].min()
print(f"第一行緯度變化: {lat_row_variation:.4f} 度")
print(f"第一列經度變化: {lon_col_variation:.4f} 度")

if lat_row_variation > 0.5 or lon_col_variation > 0.5:
    print("=> 這是 CURVILINEAR (曲線) 網格，不是正規經緯度網格")
else:
    print("=> 這是近似正規網格")

ds.close()
