from concurrent.futures import ThreadPoolExecutor

import numpy as np
import xarray as xr

import app_v2


def _sample_dataset() -> xr.Dataset:
    values = np.array(
        [
            [[280.0, 281.0], [282.0, 283.0]],
            [[284.0, 285.0], [286.0, 287.0]],
            [[288.0, 289.0], [290.0, 291.0]],
        ],
        dtype=np.float32,
    )
    return xr.Dataset(
        data_vars={
            "T2": (("Time", "south_north", "west_east"), values),
            "U10": (("Time", "south_north", "west_east"), np.ones_like(values) * 3.0),
            "V10": (("Time", "south_north", "west_east"), np.ones_like(values) * 4.0),
            "XLAT": (("Time", "south_north", "west_east"), np.repeat(np.array([[[24.0, 24.0], [25.0, 25.0]]], dtype=np.float32), 3, axis=0)),
            "XLONG": (("Time", "south_north", "west_east"), np.repeat(np.array([[[120.0, 121.0], [120.0, 121.0]]], dtype=np.float32), 3, axis=0)),
        },
        coords={"Time": [0, 1, 2]},
    )


def test_time_series_returns_values_for_nearest_grid_point(monkeypatch):
    ds = _sample_dataset()
    lats = np.array([[24.0, 24.0], [25.0, 25.0]], dtype=np.float32)
    lons = np.array([[120.0, 121.0], [120.0, 121.0]], dtype=np.float32)

    monkeypatch.setattr(app_v2, "get_dataset", lambda: ds)
    monkeypatch.setattr(app_v2, "get_coordinates", lambda _: (lons, lats))

    res = app_v2.app.test_client().get("/time_series?lat=25&lon=121&variable=T2")

    assert res.status_code == 200
    body = res.get_json()
    assert body["variable"] == "2米溫度"
    assert body["units"] == "°C"
    assert body["gridLat"] == 25.0
    assert body["gridLon"] == 121.0
    assert body["values"] == [9.85, 13.85, 17.85]


def test_time_series_supports_derived_wind_speed(monkeypatch):
    ds = _sample_dataset()
    lats = np.array([[24.0, 24.0], [25.0, 25.0]], dtype=np.float32)
    lons = np.array([[120.0, 121.0], [120.0, 121.0]], dtype=np.float32)

    monkeypatch.setattr(app_v2, "get_dataset", lambda: ds)
    monkeypatch.setattr(app_v2, "get_coordinates", lambda _: (lons, lats))

    res = app_v2.app.test_client().get("/time_series?lat=24&lon=120&variable=WSPD")

    assert res.status_code == 200
    body = res.get_json()
    assert body["values"] == [5.0, 5.0, 5.0]
    assert body["units"] == "m/s"


def test_dataset_bounds_handles_antimeridian_wrapped_longitudes():
    lons = np.array([[170.0, 179.0], [-179.0, -170.0]], dtype=np.float32)
    lats = np.array([[10.0, 12.0], [14.0, 16.0]], dtype=np.float32)

    assert app_v2.dataset_bounds(lons, lats) == [170.0, 10.0, 190.0, 16.0]


def test_dataset_bounds_keeps_regular_regional_longitudes():
    lons = np.array([[120.0, 121.0], [120.5, 121.5]], dtype=np.float32)
    lats = np.array([[24.0, 24.0], [25.0, 25.0]], dtype=np.float32)

    assert app_v2.dataset_bounds(lons, lats) == [120.0, 24.0, 121.5, 25.0]


def test_coords_texture_headers_use_continuous_antimeridian_longitudes(monkeypatch):
    ds = _sample_dataset()
    lons = np.array([[170.0, 179.0], [-179.0, -170.0]], dtype=np.float32)
    lats = np.array([[10.0, 12.0], [14.0, 16.0]], dtype=np.float32)

    app_v2.coords_texture_cache.clear()
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", "/tmp/wrfout_d01_test")
    monkeypatch.setattr(app_v2, "get_dataset", lambda: ds)
    monkeypatch.setattr(app_v2, "get_coordinates", lambda _: (lons, lats))

    res = app_v2.app.test_client().get("/coords_texture?time=0")

    assert res.status_code == 200
    assert res.headers["X-Coords-Lon-Range"] == "170.000000,190.000000"


def test_resolve_dataset_path_falls_back_to_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    wrf_file = data_dir / "wrfout_d01_2026-09-02_00:00:00"
    wrf_file.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(app_v2, "DATA_DIR", str(data_dir))
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(tmp_path / "missing_wrfout"))

    assert app_v2.resolve_dataset_path() == str(wrf_file)
    assert app_v2._CURRENT_FILE["path"] == str(wrf_file)


def test_ready_reports_ready_when_dataset_is_usable(tmp_path, monkeypatch):
    wrf_file = tmp_path / "wrfout_d01_2026-09-02_00:00:00"
    wrf_file.write_text("placeholder", encoding="utf-8")

    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(wrf_file))
    monkeypatch.setattr(app_v2, "get_dataset", _sample_dataset)

    res = app_v2.app.test_client().get("/ready")

    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ready"
    assert body["checks"]["dataset"]["ok"] is True
    assert body["checks"]["coordinates"]["ok"] is True
    assert body["checks"]["variables"]["count"] >= 3


def test_ready_returns_503_when_dataset_is_missing(tmp_path, monkeypatch):
    empty_data_dir = tmp_path / "data"
    empty_data_dir.mkdir()

    monkeypatch.setattr(app_v2, "DATA_DIR", str(empty_data_dir))
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(tmp_path / "missing_wrfout"))

    res = app_v2.app.test_client().get("/ready")

    assert res.status_code == 503
    assert res.get_json()["status"] == "not_ready"


def test_version_reports_build_identity(monkeypatch, tmp_path):
    wrf_file = tmp_path / "wrfout_d01_2026-09-02_00:00:00"
    wrf_file.write_text("placeholder", encoding="utf-8")
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(wrf_file))
    monkeypatch.setattr(app_v2, "BUILD_VERSION", "1.2.3")
    monkeypatch.setattr(app_v2, "BUILD_SHA", "abc123")
    monkeypatch.setattr(app_v2, "BUILD_DATE", "2026-09-02T00:00:00Z")

    res = app_v2.app.test_client().get("/version")

    assert res.status_code == 200
    body = res.get_json()
    assert body["service"] == "maritime-platform-backend"
    assert body["version"] == "1.2.3"
    assert body["gitSha"] == "abc123"
    assert body["buildDate"] == "2026-09-02T00:00:00Z"
    assert body["dataset"] == wrf_file.name


def test_operational_security_headers_are_set():
    res = app_v2.app.test_client().get("/health")

    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "X-Response-Time-ms" in res.headers


def test_metrics_endpoint_exposes_prometheus_text():
    client = app_v2.app.test_client()
    client.get("/health")

    res = client.get("/metrics")
    body = res.get_data(as_text=True)

    assert res.status_code == 200
    assert "text/plain" in res.headers["Content-Type"]
    assert "maritime_http_requests_total" in body
    assert "maritime_http_request_duration_seconds_sum" in body
    assert "maritime_http_rate_limited_total" in body
    assert 'maritime_http_requests_by_status_class_total{status_class="2xx"}' in body
    assert "maritime_tile_cache_entries" in body


def test_api_key_gate_is_optional_by_default(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)

    res = app_v2.app.test_client().get("/metrics")

    assert res.status_code == 200


def test_api_key_gate_blocks_private_endpoints(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    res = app_v2.app.test_client().get("/metrics")

    assert res.status_code == 401
    assert res.get_json()["error"] == "Unauthorized"


def test_api_key_gate_accepts_x_api_key_header(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    res = app_v2.app.test_client().get("/metrics", headers={"X-API-Key": "secret-test-key"})

    assert res.status_code == 200


def test_api_key_gate_accepts_bearer_token(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    res = app_v2.app.test_client().get(
        "/metrics",
        headers={"Authorization": "Bearer secret-test-key"},
    )

    assert res.status_code == 200


def test_api_key_gate_keeps_readiness_public(monkeypatch, tmp_path):
    empty_data_dir = tmp_path / "data"
    empty_data_dir.mkdir()
    monkeypatch.setenv("API_KEY", "secret-test-key")
    monkeypatch.setattr(app_v2, "DATA_DIR", str(empty_data_dir))
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(tmp_path / "missing_wrfout"))

    res = app_v2.app.test_client().get("/ready")

    assert res.status_code == 503
    assert res.get_json()["status"] == "not_ready"


def test_api_key_gate_keeps_version_public(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-test-key")

    res = app_v2.app.test_client().get("/version")

    assert res.status_code == 200


def test_rate_limit_is_optional_by_default(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    app_v2.RATE_LIMIT_BUCKETS.clear()

    client = app_v2.app.test_client()

    assert client.get("/metrics").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_rate_limit_blocks_after_configured_threshold(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    app_v2.RATE_LIMIT_BUCKETS.clear()

    client = app_v2.app.test_client()

    assert client.get("/metrics").status_code == 200
    assert client.get("/metrics").status_code == 200
    limited = client.get("/metrics")

    assert limited.status_code == 429
    assert limited.get_json()["error"] == "Rate limit exceeded"
    assert "Retry-After" in limited.headers


def test_rate_limit_keeps_readiness_public(monkeypatch, tmp_path):
    empty_data_dir = tmp_path / "data"
    empty_data_dir.mkdir()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setattr(app_v2, "DATA_DIR", str(empty_data_dir))
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(tmp_path / "missing_wrfout"))
    app_v2.RATE_LIMIT_BUCKETS.clear()

    client = app_v2.app.test_client()

    assert client.get("/ready").status_code == 503
    assert client.get("/ready").status_code == 503


def test_select_netcdf_file_rejects_paths_outside_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    outside_file = tmp_path / "wrfout_d01_outside"
    outside_file.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(app_v2, "DATA_DIR", str(data_dir))

    res = app_v2.app.test_client().post(
        "/netcdf_files/select",
        json={"path": str(outside_file)},
    )

    assert res.status_code == 404
    assert res.get_json()["error"] == "Not found"


def test_select_netcdf_file_accepts_candidates_inside_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    wrf_file = data_dir / "wrfout_d01_inside"
    wrf_file.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(app_v2, "DATA_DIR", str(data_dir))
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(data_dir / "initial_wrfout"))
    monkeypatch.setattr(app_v2, "trigger_etl_for_file", lambda *_: False)

    res = app_v2.app.test_client().post(
        "/netcdf_files/select",
        json={"path": str(wrf_file)},
    )

    assert res.status_code == 200
    assert res.get_json()["current"] == str(wrf_file.resolve())


def test_dynamic_tiles_survive_concurrent_requests(monkeypatch, tmp_path):
    ds = _sample_dataset()
    lats = np.array([[24.0, 24.0], [25.0, 25.0]], dtype=np.float32)
    lons = np.array([[120.0, 121.0], [120.0, 121.0]], dtype=np.float32)
    wrf_file = tmp_path / "wrfout_d01_concurrent"
    wrf_file.write_text("placeholder", encoding="utf-8")

    app_v2.tile_cache.clear()
    monkeypatch.setitem(app_v2._CURRENT_FILE, "path", str(wrf_file))
    monkeypatch.setattr(app_v2, "get_dataset", lambda: ds)
    monkeypatch.setattr(app_v2, "get_coordinates", lambda _: (lons, lats))

    tile = app_v2.mercantile.tile(120.5, 24.5, 6)
    path = f"/tiles/{tile.z}/{tile.x}/{tile.y}?variable=T2&time=0&vmin=0&vmax=30"

    def request_tile():
        res = app_v2.app.test_client().get(path)
        return res.status_code, res.headers.get("Content-Type", ""), len(res.data)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: request_tile(), range(20)))

    assert all(status == 200 for status, _, _ in results)
    assert all("image/png" in content_type for _, content_type, _ in results)
    assert all(size > 100 for _, _, size in results)
