#!/usr/bin/env python3
"""Sync local media/dist/ to the Railway volume mounted at /data.

Wipes /data first to mirror the local build (build.py recreates media/dist/
from scratch, so removed photos get cleaned up on the server too).
"""

import subprocess
import sys
from pathlib import Path

DIST = Path(__file__).parent / "media" / "dist"

if not DIST.exists() or not any(DIST.iterdir()):
    sys.exit(f"No build output at {DIST}. Run `python3 build.py` first.")

print(f"Uploading {DIST} → /data on Railway service map-gallery...")
remote = "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf - -C /data"
tar = subprocess.Popen(
    ["tar", "czf", "-", "-C", str(DIST), "."],
    stdout=subprocess.PIPE,
)
ssh = subprocess.Popen(
    ["railway", "ssh", "--service", "map-gallery", "--", "bash", "-c", remote],
    stdin=tar.stdout,
)
tar.stdout.close()
ssh.wait()
sys.exit(ssh.returncode)
