#!/usr/bin/env python3
"""Build script: extracts photo metadata, generates thumbnails, parses routes."""

import json
import re
import shutil
import subprocess
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
VIDEO_DIR = DIST / "videos"
THUMB_SIZE = (150, 150)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}

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


def iter_media_files(extensions):
    """Yield files from PHOTOS_DIR matching the given extensions."""
    for f in sorted(PHOTOS_DIR.iterdir()):
        if f.suffix.lower() not in extensions or "Zone.Identifier" in f.name:
            continue
        if f.is_file():
            yield f


PHOTO_EXTENSIONS = {
    ext for ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}
} - {".dng"}


def process_photos():
    """Extract GPS, date; generate thumbnails; copy full images."""
    photos = []

    for f in iter_media_files(PHOTO_EXTENSIONS):

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
            "type": "photo",
        })

    # Sort chronologically
    photos.sort(key=lambda p: p["date"])
    return photos


def process_videos():
    """Extract GPS, date from videos; generate thumbnail screenshots; copy videos."""
    videos = []

    for f in iter_media_files(VIDEO_EXTENSIONS):

        # Get metadata via ffprobe
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", f],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  Skipping {f.name} (ffprobe failed)")
            continue

        fmt = json.loads(result.stdout).get("format", {})
        tags = fmt.get("tags", {})

        # Parse GPS from location tag (e.g. "+52.016649+127.743537/")
        location = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
        if not location:
            print(f"  Skipping {f.name} (no GPS data)")
            continue

        m = re.match(r"([+-][\d.]+)([+-][\d.]+)", location)
        if not m:
            print(f"  Skipping {f.name} (cannot parse location: {location})")
            continue

        lat = float(m.group(1))
        lon = float(m.group(2))

        # Parse date — normalize to YYYY:MM:DD HH:MM:SS to match EXIF format
        creation_time = tags.get("creation_time", "")
        date_str = creation_time.replace("T", " ").replace("Z", "").split(".")[0] if creation_time else ""
        if date_str:
            date_str = date_str.replace("-", ":", 2)

        # Description from comment tag
        desc_str = tags.get("comment", "").strip()

        # Generate thumbnail from first few seconds (suffix avoids collision with photo thumbs)
        thumb_name = f.stem + "_video.jpg"
        thumb_path = THUMB_DIR / thumb_name
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1", "-i", str(f), "-vframes", "1",
             "-vf", f"scale={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:force_original_aspect_ratio=decrease",
             str(thumb_path)],
            capture_output=True,
        )
        if not thumb_path.exists():
            print(f"  Skipping {f.name} (thumbnail generation failed)")
            continue

        # Copy video
        shutil.copy2(f, VIDEO_DIR / f.name)

        videos.append({
            "filename": f.name,
            "thumb": f"thumbnails/{thumb_name}",
            "video": f"videos/{f.name}",
            "lat": lat,
            "lon": lon,
            "date": date_str,
            "description": desc_str,
            "type": "video",
        })

    videos.sort(key=lambda v: v["date"])
    return videos


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
    VIDEO_DIR.mkdir(parents=True)

    print("Processing photos...")
    photos = process_photos()
    print(f"  {len(photos)} photos with GPS data")

    print("Processing videos...")
    videos = process_videos()
    print(f"  {len(videos)} videos with GPS data")

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
    data = {"photos": photos, "videos": videos, "routes": routes}
    with open(DIST / "data.json", "w") as f:
        json.dump(data, f)

    # Copy index.html
    shutil.copy2(ROOT / "index.html", DIST / "index.html")

    print(f"Build complete -> {DIST}")


if __name__ == "__main__":
    build()
