"""Unit tests for wind texture encoding."""

import io
import json
import numpy as np
import pytest
from PIL import Image

from wind_texture import create_coordinate_texture, encode_wind_to_png


def test_encode_wind_to_png_shape_and_metadata():
    u = np.array([[0.0, 5.0], [-3.0, 10.0]], dtype=np.float32)
    v = np.array([[1.0, -2.0], [4.0, 0.0]], dtype=np.float32)

    buf, meta = encode_wind_to_png(u, v)

    assert isinstance(buf, io.BytesIO)
    assert meta["width"] == 2
    assert meta["height"] == 2
    assert meta["u_min"] <= meta["u_max"]
    assert meta["v_min"] <= meta["v_max"]

    img = Image.open(buf)
    assert img.size == (2, 2)
    assert img.mode == "RGBA"


def test_create_coordinate_texture_roundtrip_ranges():
    lons = np.array([[120.0, 121.0], [120.5, 121.5]])
    lats = np.array([[24.0, 24.1], [24.2, 24.3]])

    raw, meta = create_coordinate_texture(lons, lats)

    assert meta["width"] == 2
    assert meta["height"] == 2
    assert meta["min_lon"] == pytest.approx(120.0)
    assert meta["max_lon"] == pytest.approx(121.5)
    assert meta["min_lat"] == pytest.approx(24.0)
    assert meta["max_lat"] == pytest.approx(24.3)
    assert len(raw) == 2 * 2 * 4


def test_encode_wind_handles_nan():
    u = np.array([[np.nan, 1.0]], dtype=np.float32)
    v = np.array([[2.0, np.nan]], dtype=np.float32)

    buf, meta = encode_wind_to_png(u, v)

    assert meta["width"] == 2
    assert meta["height"] == 1
    img = Image.open(buf)
    assert img.size == (2, 1)
