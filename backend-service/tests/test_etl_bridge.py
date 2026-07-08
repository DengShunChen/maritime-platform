"""Unit tests for ETL bridge state (no GDAL conversion)."""

import os

from etl_bridge import get_etl_status, trigger_etl_for_file


def test_get_etl_status_defaults():
    status = get_etl_status()
    assert "running" in status
    assert status["running"] is False


def test_trigger_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("ETL_AUTO", "false")
    assert trigger_etl_for_file("/nonexistent/wrfout") is False


def test_trigger_skipped_missing_file(monkeypatch):
    monkeypatch.setenv("ETL_AUTO", "true")
    assert trigger_etl_for_file("/nonexistent/wrfout_d01") is False
