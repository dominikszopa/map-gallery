#!/usr/bin/env python3
"""Update EXIF data of photos and videos in media/photos/ using metadata from media/exif.csv.

Updates GPS coordinates, location, and description fields.
Supports JPEG (via piexif) and MP4 (via mutagen).

Usage:
    python3 update_exif.py              # dry-run (default)
    python3 update_exif.py --write      # actually write changes
"""

import csv
import os
import struct
import sys

import piexif
from mutagen.mp4 import MP4
from PIL import Image

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "media", "photos")
CSV_PATH = os.path.join(os.path.dirname(__file__), "media", "exif.csv")


def decimal_to_dms(decimal):
    """Convert decimal degrees to (degrees, minutes, seconds) as rationals for EXIF."""
    decimal = abs(decimal)
    degrees = int(decimal)
    minutes_full = (decimal - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60 * 10000)
    return ((degrees, 1), (minutes, 1), (seconds, 10000))


def parse_gps(gps_string):
    """Parse 'lat, lon' string into floats."""
    parts = gps_string.split(",")
    if len(parts) != 2:
        return None, None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        return lat, lon
    except ValueError:
        return None, None


def build_gps_ifd(lat, lon):
    """Build EXIF GPS IFD dict from lat/lon floats."""
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude: decimal_to_dms(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude: decimal_to_dms(lon),
    }
    return gps_ifd


def encode_user_comment(text):
    """Encode a string as EXIF UserComment with Unicode prefix."""
    return b"UNICODE\x00" + text.encode("utf-16-le")


def update_photo(filepath, lat, lon, location, description, dry_run=True):
    """Update EXIF data for a single photo."""
    try:
        exif_dict = piexif.load(filepath)
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    changes = []

    if lat is not None and lon is not None:
        exif_dict["GPS"] = build_gps_ifd(lat, lon)
        changes.append(f"GPS: {lat}, {lon}")

    # Combine description and location into ImageDescription
    desc_parts = []
    if description:
        desc_parts.append(description)
    if location:
        desc_parts.append(location)

    if desc_parts:
        full_desc = " - ".join(desc_parts)
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = full_desc.encode("utf-8")
        changes.append(f"Description: {full_desc[:60]}...")

        # Also write UserComment in Exif IFD for broader compatibility
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = encode_user_comment(full_desc)

    if not changes:
        return False

    label = "[DRY RUN] " if dry_run else ""
    print(f"  {label}{os.path.basename(filepath)}")
    for c in changes:
        print(f"    {c}")

    if not dry_run:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, filepath)

    return True


def update_mp4(filepath, lat, lon, location, description, dry_run=True):
    """Update metadata for a single MP4 file."""
    changes = []

    mp4 = MP4(filepath)

    if lat is not None and lon is not None:
        # ISO 6709 format: +DD.DDDD+DDD.DDDD/
        lat_sign = "+" if lat >= 0 else ""
        lon_sign = "+" if lon >= 0 else ""
        iso6709 = f"{lat_sign}{lat:.6f}{lon_sign}{lon:.6f}/"
        mp4["\xa9xyz"] = [iso6709]
        changes.append(f"GPS: {lat}, {lon}")

    desc_parts = []
    if description:
        desc_parts.append(description)
    if location:
        desc_parts.append(location)

    if desc_parts:
        full_desc = " - ".join(desc_parts)
        mp4["\xa9des"] = [full_desc]
        mp4["\xa9cmt"] = [full_desc]
        changes.append(f"Description: {full_desc[:60]}...")

    if not changes:
        return False

    label = "[DRY RUN] " if dry_run else ""
    print(f"  {label}{os.path.basename(filepath)}")
    for c in changes:
        print(f"    {c}")

    if not dry_run:
        mp4.save()

    return True


def main():
    dry_run = "--write" not in sys.argv

    if dry_run:
        print("DRY RUN - no files will be modified. Use --write to apply changes.\n")
    else:
        print("WRITING EXIF data to photos.\n")

    if not os.path.isfile(CSV_PATH):
        print(f"Error: CSV not found at {CSV_PATH}")
        sys.exit(1)

    updated = 0
    skipped = 0
    not_found = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = (row.get("Filename") or "").strip()
            if not filename:
                skipped += 1
                continue

            filepath = os.path.join(PHOTOS_DIR, filename)
            if not os.path.isfile(filepath):
                print(f"  NOT FOUND: {filename}")
                not_found += 1
                continue

            gps = (row.get("GPS Coordinates") or "").strip()
            location = (row.get("Location") or "").strip()
            description = (row.get("Description") or "").strip()

            lat, lon = parse_gps(gps) if gps else (None, None)

            if not lat and not location and not description:
                skipped += 1
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext == ".mp4":
                if update_mp4(filepath, lat, lon, location, description, dry_run):
                    updated += 1
            else:
                if update_photo(filepath, lat, lon, location, description, dry_run):
                    updated += 1

    print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Not found: {not_found}")


if __name__ == "__main__":
    main()
