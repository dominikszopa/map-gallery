#!/usr/bin/env python3
"""Build script: extracts photo metadata, generates thumbnails, parses routes."""

import json
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import exifread
from PIL import Image

ROOT = Path(__file__).parent
MEDIA = ROOT / "media"
PHOTOS_DIR = MEDIA / "photos"
ROUTES_DIR = MEDIA / "routes"
DIST = MEDIA / "dist"
THUMB_DIR = DIST / "thumbnails"
FULL_DIR = DIST / "photos"
THUMB_SIZE = (150, 150)

KML_NS = "http://www.opengis.net/kml/2.2"


def dms_to_decimal(dms_value, ref):
    """Convert EXIF GPS DMS to decimal degrees."""
    d = float(dms_value.values[0].num) / float(dms_value.values[0].den)
    m = float(dms_value.values[1].num) / float(dms_value.values[1].den)
    s = float(dms_value.values[2].num) / float(dms_value.values[2].den)
    decimal = d + m / 60 + s / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def process_photos():
    """Extract GPS, date; generate thumbnails; copy full images."""
    photos = []
    skip_ext = {".dng"}

    for f in sorted(PHOTOS_DIR.iterdir()):
        if f.suffix.lower() in skip_ext or "Zone.Identifier" in f.name:
            continue
        if not f.is_file():
            continue

        with open(f, "rb") as fh:
            tags = exifread.process_file(fh, details=False)

        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        if not all([lat_tag, lat_ref, lon_tag, lon_ref]):
            print(f"  Skipping {f.name} (no GPS data)")
            continue

        lat = dms_to_decimal(lat_tag, str(lat_ref))
        lon = dms_to_decimal(lon_tag, str(lon_ref))

        date_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        date_str = str(date_tag) if date_tag else ""

        desc_tag = tags.get("Image ImageDescription")
        desc_str = str(desc_tag).strip() if desc_tag else ""

        # Generate thumbnail (with EXIF orientation correction)
        thumb_name = f.stem + ".jpg"
        with Image.open(f) as img:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
            img.thumbnail(THUMB_SIZE)
            img.save(THUMB_DIR / thumb_name, "JPEG", quality=85)

        # Copy full image
        shutil.copy2(f, FULL_DIR / f.name)

        photos.append({
            "filename": f.name,
            "thumb": f"thumbnails/{thumb_name}",
            "full": f"photos/{f.name}",
            "lat": lat,
            "lon": lon,
            "date": date_str,
            "description": desc_str,
        })

    # Sort chronologically
    photos.sort(key=lambda p: p["date"])
    return photos


def parse_kmz(kmz_path):
    """Parse a KMZ file into route lines and waypoints."""
    with zipfile.ZipFile(kmz_path) as z:
        with z.open("doc.kml") as f:
            root = ET.parse(f).getroot()

    doc_name_el = root.find(f".//{{{KML_NS}}}Document/{{{KML_NS}}}name")
    route_name = doc_name_el.text if doc_name_el is not None else kmz_path.stem

    lines = []
    for pm in root.iter(f"{{{KML_NS}}}Placemark"):
        ls = pm.find(f".//{{{KML_NS}}}LineString")
        if ls is None:
            continue
        name_el = pm.find(f"{{{KML_NS}}}name")
        coords_text = ls.find(f"{{{KML_NS}}}coordinates").text.strip()
        coords = []
        for point in coords_text.split():
            parts = point.split(",")
            lon, lat = float(parts[0]), float(parts[1])
            coords.append([lat, lon])
        # Downsample long routes to keep data.json small
        if len(coords) > 2000:
            step = len(coords) // 2000
            coords = coords[::step] + [coords[-1]]

        lines.append({
            "name": name_el.text if name_el is not None else "Unnamed",
            "coords": coords,
        })

    return {"name": route_name, "lines": lines}


def build():
    # Clean and create output dirs
    if DIST.exists():
        shutil.rmtree(DIST)
    THUMB_DIR.mkdir(parents=True)
    FULL_DIR.mkdir(parents=True)

    print("Processing photos...")
    photos = process_photos()
    print(f"  {len(photos)} photos with GPS data")

    print("Processing routes...")
    routes = []
    for kmz in sorted(ROUTES_DIR.glob("*.kmz")):
        if "Zone.Identifier" in kmz.name:
            continue
        route = parse_kmz(kmz)
        routes.append(route)
        total_points = sum(len(l["coords"]) for l in route["lines"])
        print(f"  {route['name']}: {len(route['lines'])} lines, {total_points} points")

    # Write data
    data = {"photos": photos, "routes": routes}
    with open(DIST / "data.json", "w") as f:
        json.dump(data, f)

    # Copy index.html
    shutil.copy2(ROOT / "index.html", DIST / "index.html")

    print(f"Build complete -> {DIST}")


if __name__ == "__main__":
    build()
