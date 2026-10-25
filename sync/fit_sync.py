#!/usr/bin/env python3
"""Upload new FIT files (Zwift rides, HealthFit workouts) from this Mac to LockedIn.

Standard library only, so it runs under the system /usr/bin/python3 from launchd.
Config: ~/.config/lockedin/sync.env (KEY=VALUE lines), overridable by environment:
  LOCKEDIN_API          e.g. https://lockedin.vercel.app
  SYNC_TOKEN            same value as the server's SYNC_TOKEN
  ZWIFT_ACTIVITIES_DIR  default ~/Documents/Zwift/Activities
  HEALTHFIT_DIR         HealthFit's iCloud Drive export folder (optional)
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "lockedin" / "sync.env"
MAX_BYTES = 4_000_000
BATCH = 500
MAX_DEPTH = 3
MIN_AGE_S = 60
WAIT_S = 90
MAX_WAITS = 10
SKIP_NAMES = {"inprogressactivity.fit"}  # Zwift's partial file during a ride

Http = Callable[[str, str, bytes, dict], tuple[int, bytes]]


@dataclass
class SyncReport:
    uploaded: int = 0
    duplicates: int = 0
    pending: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("LOCKEDIN_API", "SYNC_TOKEN", "ZWIFT_ACTIVITIES_DIR", "HEALTHFIT_DIR"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def folders_from(cfg: dict) -> list[tuple[Path, str]]:
    zwift = cfg.get("ZWIFT_ACTIVITIES_DIR") or "~/Documents/Zwift/Activities"
    folders = [(Path(zwift).expanduser(), "zwift")]
    if cfg.get("HEALTHFIT_DIR"):
        folders.append((Path(cfg["HEALTHFIT_DIR"]).expanduser(), "healthfit"))
    return folders


def _walk(folder: Path, depth: int = 0):
    for p in sorted(folder.iterdir()):
        if p.is_dir() and depth < MAX_DEPTH and not p.name.startswith("."):
            yield from _walk(p, depth + 1)
        elif p.is_file():
            yield p


def candidate_files(folders: list[tuple[Path, str]], now: float, min_age_s: int = MIN_AGE_S,
                    pending: list | None = None) -> tuple[list[tuple[Path, str]], list[str]]:
    """New-looking FIT files per folder; files modified too recently are appended to `pending`."""
    files: list[tuple[Path, str]] = []
    warnings: list[str] = []
    for folder, label in folders:
        try:
            if not folder.is_dir():
                warnings.append(f"Folder not found or not readable: {folder}. Check the path in {CONFIG_FILE}.")
                continue
            for p in _walk(folder):
                name = p.name
                if name.startswith(".") or not name.lower().endswith(".fit") or name.lower() in SKIP_NAMES:
                    continue  # also skips iCloud placeholders (.name.fit.icloud)
                st = p.stat()
                if st.st_mtime > now - min_age_s:
                    if pending is not None:
                        pending.append(p)  # still being written
                    continue
                if st.st_size > MAX_BYTES:
                    warnings.append(f"Skipped {p}: larger than 4 MB, upload it by hand if needed.")
                    continue
                files.append((p, label))
        except PermissionError:
            warnings.append(
                f"Can't read {folder}: give Full Disk Access to {os.path.realpath(sys.executable)} "
                "(System Settings → Privacy & Security → Full Disk Access). See README."
            )
        except OSError as e:
            warnings.append(f"Can't read {folder}: {e}")
    return files, warnings


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def icloud_download(path: Path) -> None:
    """Ask iCloud Drive to bring an evicted file back to this Mac; it is retried on the next pass."""
    subprocess.run(["/usr/bin/brctl", "download", str(path)], capture_output=True, timeout=30, check=False)


def urllib_http(url: str, token: str, body: bytes, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={**headers, "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _multipart(filename: str, data: bytes, source: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="source"\r\n\r\n{source}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def sync_once(cfg: dict, now: float, http: Http = urllib_http) -> SyncReport:
    report = SyncReport()
    api, token = cfg.get("LOCKEDIN_API", "").rstrip("/"), cfg.get("SYNC_TOKEN", "")
    if not api or not token:
        report.errors.append(f"LOCKEDIN_API and SYNC_TOKEN must be set in {CONFIG_FILE}.")
        return report

    pending: list = []
    files, report.warnings = candidate_files(folders_from(cfg), now, pending=pending)
    report.pending = len(pending)
    hashed = []
    for p, label in files:
        try:
            hashed.append((p, label, sha256_file(p)))
        except OSError as e:
            if e.errno == errno.EDEADLK:  # iCloud placeholder ("Optimize Mac Storage"); fetch it, retry soon
                icloud_download(p)
                report.pending += 1
            else:
                report.warnings.append(f"Skipped {p.name} for now, couldn't read it: {e}")
    try:
        known: set[str] = set()
        for i in range(0, len(hashed), BATCH):
            body = json.dumps({"hashes": [h for _, _, h in hashed[i:i + BATCH]]}).encode()
            status, resp = http(f"{api}/api/fit/known", token, body, {"Content-Type": "application/json"})
            if status != 200:
                report.errors.append(f"Server said {status} when checking files: {resp[:200]!r}")
                return report
            known |= set(json.loads(resp)["known"])

        for path, label, digest in hashed:
            if digest in known:
                report.duplicates += 1
                continue
            body, ctype = _multipart(path.name, path.read_bytes(), label)
            status, resp = http(f"{api}/api/fit/upload", token, body, {"Content-Type": ctype})
            try:
                result = json.loads(resp) if resp else {}
            except ValueError:
                result = {}
            if status == 401:
                report.errors.append("Server said 401: SYNC_TOKEN doesn't match the server's. Stopped.")
                return report
            if status != 200:
                detail = result.get("detail") or resp[:120].decode("utf-8", "replace")
                report.errors.append(f"{path.name}: server said {status} {detail}")
            elif result.get("status") == "imported":
                report.uploaded += 1
            elif result.get("status") in ("duplicate", "empty"):  # empty: a ride started and quit
                report.duplicates += 1
            else:
                report.errors.append(f"{path.name}: {result.get('error') or 'import failed'}")
    except (OSError, ValueError) as e:
        report.errors.append(f"Stopped, will retry next run: {e}")
    return report


def run(cfg: dict, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
        http: Http = urllib_http) -> list[SyncReport]:
    """Sync, then keep waiting a bit while files are still being written (launchd fires on the first write)."""
    reports = [sync_once(cfg, now(), http=http)]
    while reports[-1].pending and not reports[-1].errors and len(reports) <= MAX_WAITS:
        sleep(WAIT_S)
        reports.append(sync_once(cfg, now(), http=http))
    return reports


def main() -> int:
    try:
        reports = run(load_config())
    except Exception as e:  # launchd swallows tracebacks; always leave a readable line in the log
        print(f"{datetime.now().isoformat(timespec='seconds')} sync failed: {e!r}")
        return 0
    for report in reports:
        stamp = datetime.now().isoformat(timespec="seconds")
        print(f"{stamp} uploaded {report.uploaded}, already there {report.duplicates}, "
              f"waiting (being written or downloading from iCloud) {report.pending}, errors {len(report.errors)}")
        for line in report.warnings + report.errors:
            print(f"{stamp}   {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
