# Maritime Platform - Project Roadmap & Task List

## 🎯 Executive Summary
**Current Status**: Beta 2.0 (Stable). Core 2D visualization (Raster heatmaps, Contours, Data Inspector) is functional.
**Recent Incident**: Attempted performance optimization and 3D integration in Sprint 1 caused critical regressions (missing color maps, broken wind synthesis, Nginx routing errors). Changes were rolled back.
**PM Directive**: Feature freeze on advanced visualizations (WebGL Wind, 3D Slicing) until a comprehensive automated testing framework is established.

---

## 🟢 Sprint 2: Stability & Test Infrastructure (Active)
**Goal**: Build a safety net. No more "it works on my machine" deployments. Every endpoint must be automatically verified before the frontend can connect to it.

### [ ] Task 2.1: Automated Backend QA Gate (qa_test.py)
**Description**: Recreate and enhance the `qa_test.py` script to intercept bad deployments. It must test 100% of the API endpoints for 200 OK statuses and valid JSON/PNG responses.
**Acceptance Criteria**:
- Script covers `/health`, `/variables`, `/time_points`, `/netcdf_files`.
- Script probes native variables (T2, PSFC) and synthetic variables (WSPD).
- Script verifies dynamic tile generation (`/tiles/z/x/y`) and handles matplotlib thread safety checks.
- Build fails if the script exits with code 1.

### [ ] Task 2.2: Matplotlib Thread-Safety Hardening
**Description**: Matplotlib is not thread-safe. Concurrent tile requests from the frontend cause 500 errors. We need to implement a robust locking mechanism or move to a process-pool/headless renderer for tiles before adding caching.
**Acceptance Criteria**:
- `backend-service/app_v2.py` uses a `threading.Lock()` around all `plt.subplots()` and `ax.pcolormesh()` calls.
- Load test with 50 concurrent tile requests passes without 500 errors.

### [ ] Task 2.3: Frontend Error Boundary & Graceful Degradation
**Description**: If a tile fails to load, the entire map shouldn't go black. The UI needs to handle API 404/500 errors gracefully.
**Acceptance Criteria**:
- `MapView.tsx` catches fetch errors and displays a user-friendly Toast message instead of crashing or showing a blank screen.
- Wind controls are permanently disabled/hidden if the `/wind_texture` API is unreachable.

---

## 🟡 Sprint 3: Safe Re-introduction of Advanced Features (Next)
**Goal**: Carefully bring back the performance improvements and the WebGL Wind Particles, backed by our new test suite.

### [ ] Task 3.1: Re-enable WebGL Wind Particles
**Description**: The WebGL wind layer requires `/wind_texture` and `/coords_texture`.
**Acceptance Criteria**:
- Ensure `U` and `V` (or `U10`/`V10`) are correctly extracted from NetCDF/GRIB2.
- `coords_texture` returns correct `X-Coords-Grid-Size` headers without xarray truth-value ambiguity errors.
- Wind toggle button is restored in `LayerPanel.tsx`.

### [ ] Task 3.2: LRU Caching for Dynamic Tiles
**Description**: Implement memory caching to prevent redundant matplotlib rendering for previously visited map regions.
**Acceptance Criteria**:
- `functools.lru_cache` applied safely *outside* the Flask route decorator.
- Cache keys include variable name, time index, zoom, x, y, and vertical level.
- Cache is cleared when a new NetCDF file is selected.

### [ ] Task 3.3: 3D Vertical Profiling (Level Slicing)
**Description**: Allow users to view atmospheric data at different altitudes (e.g., 850hPa).
**Acceptance Criteria**:
- Backend APIs accept a `level` parameter and slice the `bottom_top` dimension.
- Frontend `LayerPanel.tsx` displays a vertical slider when the selected variable has `numLevels > 1`.

---

## 🔵 Sprint 4: Military & Professional Enhancements (Later)
**Goal**: Add features specifically requested for meteorological and naval operations.

### [ ] Task 4.1: Cross-Section (Vertical Profile) Charts
**Description**: Allow clicking two points on the map to draw a line, and display a 2D vertical cross-section chart of the atmosphere along that line.

### [ ] Task 4.2: Offline / Air-Gapped Map Support
**Description**: Replace MapTiler dependency with a local MBTiles server (e.g., Martin or a local TiTiler configuration) so the system works without internet access.
