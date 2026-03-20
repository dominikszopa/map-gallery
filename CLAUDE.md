# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Serve

```bash
python3 build.py        # Process media/photos and media/routes, generate media/dist/
python3 serve.py        # Serve media/dist/ at http://localhost:8000
python3 serve.py 8080   # Optional: specify port
```

The build script requires `exifread` and `Pillow` Python packages (`pip install --user --break-system-packages exifread Pillow`).

## Architecture

This is a static map-based photo gallery. The build step processes source data into a `dist/` directory that can be served by any HTTP server.

**Build pipeline (`build.py`):**

- Reads JPEG photos from `media/photos/`, extracts GPS coordinates and dates via EXIF, generates thumbnails with orientation correction, copies originals to `media/dist/photos/`
- Parses KMZ route files from `media/routes/` (KML inside ZIP), extracts LineString geometries, downsamples to ~2000 points per line
- Outputs `media/dist/data.json` with all photo metadata and route coordinates
- Copies `index.html` into `media/dist/`
- DNG files and files without GPS data are skipped

**Frontend (`index.html`):**
- Single-page app using Leaflet.js with CARTO Voyager tiles (English labels)
- Loads `data.json` at runtime to render route polylines (one color per route) and camera icon markers at photo locations
- Hovering a camera icon shows the thumbnail; clicking opens a lightbox with prev/next navigation (arrow keys + buttons) and Escape to close
- Photos are ordered chronologically in the lightbox

**Data flow:** `media/photos/*.jpg` + `media/routes/*.kmz` → `build.py` → `media/dist/{data.json, thumbnails/, photos/, index.html}` → static HTTP server
