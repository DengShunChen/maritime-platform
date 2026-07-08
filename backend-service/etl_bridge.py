"""Background ETL bridge: WRF NetCDF → COG on file selection."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ETL_LOCK = threading.Lock()
_ETL_STATE: dict[str, Any] = {
    "running": False,
    "last_path": None,
    "last_error": None,
    "files_created": 0,
}


def _etl_enabled() -> bool:
    return os.getenv("ETL_AUTO", "true").lower() in ("1", "true", "yes")


def _import_convert_wrf_file():
    etl_dir = Path(os.getenv("ETL_DIR", "/app/etl"))
    if etl_dir.is_dir() and str(etl_dir) not in sys.path:
        sys.path.insert(0, str(etl_dir))
    from convert_grib2_to_cog import convert_wrf_file  # type: ignore[import-not-found]

    return convert_wrf_file


def get_etl_status() -> dict[str, Any]:
    with _ETL_LOCK:
        return dict(_ETL_STATE)


def trigger_etl_for_file(nc_path: str, cog_root: str | None = None) -> bool:
    """Start COG conversion in a background thread. Returns False if ETL disabled/unavailable."""
    if not _etl_enabled():
        return False

    path = Path(nc_path)
    if not path.exists():
        logger.warning("ETL skipped — file not found: %s", nc_path)
        return False

    cog_root = cog_root or os.getenv("COG_ROOT", "/cog")

    with _ETL_LOCK:
        if _ETL_STATE["running"]:
            logger.info("ETL already running for %s", _ETL_STATE["last_path"])
            return True

    def _run() -> None:
        with _ETL_LOCK:
            _ETL_STATE["running"] = True
            _ETL_STATE["last_path"] = str(path)
            _ETL_STATE["last_error"] = None
            _ETL_STATE["files_created"] = 0

        try:
            convert_wrf_file = _import_convert_wrf_file()
            created = convert_wrf_file(str(path), cog_root)
            with _ETL_LOCK:
                _ETL_STATE["files_created"] = len(created)
            logger.info("ETL finished: %d COG file(s) for %s", len(created), path.name)
        except Exception as exc:
            logger.error("ETL failed for %s: %s", path.name, exc, exc_info=True)
            with _ETL_LOCK:
                _ETL_STATE["last_error"] = str(exc)
        finally:
            with _ETL_LOCK:
                _ETL_STATE["running"] = False

    threading.Thread(target=_run, name=f"etl-{path.stem}", daemon=True).start()
    return True
