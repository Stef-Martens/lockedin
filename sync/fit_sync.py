#!/usr/bin/env python3
"""Upload new FIT files (Zwift rides, HealthFit workouts) from this Mac to LockedIn.

Standard library only, so it runs under the system /usr/bin/python3 from launchd.
Config: ~/.config/lockedin/sync.env (KEY=VALUE lines), overridable by environment:
  LOCKEDIN_API          e.g. https://lockedin.vercel.app
  SYNC_TOKEN            same value as the server's SYNC_TOKEN
  ZWIFT_ACTIVITIES_DIR  default ~/Documents/Zwift/Activities
  HEALTHFIT_DIR         HealthFit's iCloud Drive export folder (optional)
  ZWIFT_WORKOUTS_DIR    default ~/Documents/Zwift/Workouts (its one numeric subfolder, your Zwift ID)

After uploading, it also puts the Zwift workouts planned in the LockedIn agenda into that folder. It keeps a
manifest of the files it wrote and never touches any other file.

It remembers which files are already on the server in ~/Library/Application Support/lockedin/fit-sync-state.json
(LOCKEDIN_SYNC_STATE overrides the path), so those are never read or fetched from iCloud again, and files the
server couldn't read are only retried once a day. Delete that file to have everything checked again.
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
MANIFEST = ".lockedin-workouts.json"
RELEASED = "released"  # manifest value for a file of ours the owner edited: theirs now, left alone quietly
TMP_SUFFIX = ".lockedin-tmp"  # ".<name>.lockedin-tmp" while a file is being written; never a .zwo to Zwift
RETRY_UNREADABLE_S = 24 * 3600  # a file the server couldn't read is tried again a day later (maybe it's fixed)

Http = Callable[[str, str, bytes, dict], tuple[int, bytes]]


@dataclass
class SyncReport:
    uploaded: int = 0
    duplicates: int = 0
    pending: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    workouts_written: int = 0
    workouts_removed: int = 0
    stopped: bool = False  # the whole run gave up (config, network, token), not just one file


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("LOCKEDIN_API", "SYNC_TOKEN", "ZWIFT_ACTIVITIES_DIR", "HEALTHFIT_DIR", "ZWIFT_WORKOUTS_DIR"):
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


def state_file() -> Path:
    return Path(os.environ.get("LOCKEDIN_SYNC_STATE")
                or Path.home() / "Library" / "Application Support" / "lockedin" / "fit-sync-state.json")


def _load_state(path: Path) -> dict:
    """{"files": {path: [size, mtime_ns, sha256, on server]}, "failed": {sha256: retry after}}. Only a cache:
    missing or damaged just means every file is hashed and checked with the server again."""
    try:
        data = json.loads(path.read_text())
        files, failed = data.get("files"), data.get("failed")
        if isinstance(files, dict) and isinstance(failed, dict):
            return {"files": {k: v for k, v in files.items() if isinstance(v, list) and len(v) == 4
                              and isinstance(v[2], str)},
                    "failed": {h: t for h, t in failed.items() if isinstance(t, (int, float))}}
    except (OSError, ValueError, AttributeError):
        pass
    return {"files": {}, "failed": {}}


def _save_state(path: Path, state: dict) -> None:
    files = {k: v for k, v in state["files"].items() if os.path.lexists(k)}  # forget deleted files
    shas = {v[2] for v in files.values()}
    failed = {h: t for h, t in state["failed"].items() if h in shas}
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, json.dumps({"files": files, "failed": failed}, indent=1, sort_keys=True).encode())


def _unchanged(entry, st: os.stat_result) -> bool:
    return entry is not None and entry[:2] == [st.st_size, st.st_mtime_ns]


def sync_once(cfg: dict, now: float, http: Http = urllib_http) -> SyncReport:
    report = SyncReport()
    api, token = cfg.get("LOCKEDIN_API", "").rstrip("/"), cfg.get("SYNC_TOKEN", "")
    if not api or not token:
        report.errors.append(f"LOCKEDIN_API and SYNC_TOKEN must be set in {CONFIG_FILE}.")
        report.stopped = True
        return report
    where = state_file()
    state = _load_state(where)
    try:
        _upload_new(cfg, api, token, now, http, report, state)
    finally:
        try:
            _save_state(where, state)
        except OSError as e:
            report.warnings.append(f"Couldn't save {where}, so all files get checked again next run: {e}")
    return report


def _upload_new(cfg: dict, api: str, token: str, now: float, http: Http, report: SyncReport, state: dict) -> None:
    record, failed = state["files"], state["failed"]
    pending: list = []
    files, report.warnings = candidate_files(folders_from(cfg), now, pending=pending)
    report.pending = len(pending)

    def unreadable_here(p: Path, e: OSError) -> None:
        if e.errno == errno.EDEADLK:  # iCloud placeholder ("Optimize Mac Storage"); fetch it, retry soon
            icloud_download(p)
            report.pending += 1
        else:
            report.warnings.append(f"Skipped {p.name} for now, couldn't read it: {e}")

    hashed = []
    for p, label in files:
        try:
            st, entry = p.stat(), record.get(str(p))
            if _unchanged(entry, st) and entry[3]:  # on the server already: not read, not fetched from iCloud
                report.duplicates += 1
                continue
            if not _unchanged(entry, st):
                record[str(p)] = entry = [st.st_size, st.st_mtime_ns, sha256_file(p), False]
        except OSError as e:
            unreadable_here(p, e)
            continue
        if failed.get(entry[2], 0) <= now:  # else the server couldn't read it lately; wait a day
            hashed.append((p, label, entry[2]))

    def on_server(path: Path, digest: str) -> None:
        record[str(path)][3] = True
        failed.pop(digest, None)

    try:
        known: set[str] = set()
        for i in range(0, len(hashed), BATCH):
            body = json.dumps({"hashes": [h for _, _, h in hashed[i:i + BATCH]]}).encode()
            status, resp = http(f"{api}/api/fit/known", token, body, {"Content-Type": "application/json"})
            if status != 200:
                report.errors.append(f"Server said {status} when checking files: {resp[:200]!r}")
                report.stopped = True
                return
            known |= set(json.loads(resp)["known"])

        for path, label, digest in hashed:
            if digest in known:
                report.duplicates += 1
                on_server(path, digest)
                continue
            try:
                data = path.read_bytes()
            except OSError as e:
                unreadable_here(path, e)
                continue
            body, ctype = _multipart(path.name, data, label)
            status, resp = http(f"{api}/api/fit/upload", token, body, {"Content-Type": ctype})
            try:
                result = json.loads(resp) if resp else {}
            except ValueError:
                result = {}
            if status == 401:
                report.errors.append("Server said 401: SYNC_TOKEN doesn't match the server's. Stopped.")
                report.stopped = True
                return
            if status != 200:
                detail = result.get("detail") or resp[:120].decode("utf-8", "replace")
                report.errors.append(f"{path.name}: server said {status} {detail}")
            elif result.get("status") == "imported":
                report.uploaded += 1
                on_server(path, digest)
            elif result.get("status") in ("duplicate", "empty"):  # empty: a ride started and quit
                report.duplicates += 1
                on_server(path, digest)
            else:  # the server couldn't read it: say so now, try again tomorrow, not every run
                report.errors.append(f"{path.name}: {result.get('error') or 'import failed'} (retried in a day)")
                failed[digest] = now + RETRY_UNREADABLE_S
    except (OSError, ValueError) as e:
        report.errors.append(f"Stopped, will retry next run: {e}")
        report.stopped = True


def workouts_dir(cfg: dict) -> tuple[Path | None, str | None]:
    """Zwift's custom-workouts folder: the one named after the Zwift ID inside Documents/Zwift/Workouts."""
    base = Path(cfg.get("ZWIFT_WORKOUTS_DIR") or "~/Documents/Zwift/Workouts").expanduser()
    if base.name.isdigit() and base.is_dir():
        return base, None
    if not base.is_dir():
        return None, f"Zwift workouts: folder not found: {base}."
    ids = [p for p in base.iterdir() if p.is_dir() and p.name.isdigit()]
    if len(ids) == 1:
        return ids[0], None
    found = "no Zwift ID folder" if not ids else "several Zwift ID folders"
    return None, f"Zwift workouts: {found} in {base}; set ZWIFT_WORKOUTS_DIR in {CONFIG_FILE} to the right one."


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(path: Path) -> dict | None:
    """{file name: sha256, or RELEASED once the owner edited it} of the files this script wrote; None if damaged."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        return None
    return data


def _write_atomic(path: Path, data: bytes) -> None:
    """Write via a hidden temp file in the same folder, so Zwift never sees a half-written file."""
    tmp = path.with_name(f".{path.name}{TMP_SUFFIX}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _clean_temp_files(folder: Path) -> None:
    """Remove temp files a killed run left behind (only ours: hidden and ending in TMP_SUFFIX)."""
    for p in folder.iterdir():
        if p.name.startswith(".") and p.name.endswith(TMP_SUFFIX):
            try:
                p.unlink()
            except OSError:
                pass


def _save_manifest(folder: Path, state: dict) -> None:
    _write_atomic(folder / MANIFEST, json.dumps(state, indent=1, sort_keys=True).encode())


def sync_workouts(cfg: dict, http: Http = urllib_http) -> tuple[int, int, list[str]]:
    """Write the agenda's Zwift workouts into Zwift's folder and remove the ones no longer planned.

    A file is only ever replaced or deleted if the manifest says this script wrote it and it is still exactly
    what was written; anything else (the owner's own files, or ours edited in Zwift) is left alone. The
    manifest is saved after every change, so an interrupted run never loses track of a file, and files are
    written through a hidden temp file, so it never leaves a half-written one. Names are matched ignoring case,
    like the Mac's file system does, so a title whose case changed is still our file. Afterwards the
    server is told which workouts are actually in place, which is what the agenda shows as "In Zwift".
    """
    folder, problem = workouts_dir(cfg)
    if folder is None:
        return 0, 0, [problem]
    manifest = _load_manifest(folder / MANIFEST)
    if manifest is None:
        return 0, 0, [f"Zwift workouts: {folder / MANIFEST} is damaged, so no workout files were touched. "
                      "Delete it and the next run starts fresh (files it listed are then left alone)."]
    _clean_temp_files(folder)
    api, token = cfg.get("LOCKEDIN_API", "").rstrip("/"), cfg.get("SYNC_TOKEN", "")
    status, resp = http(f"{api}/api/agenda/zwift/sync", token, b"{}", {"Content-Type": "application/json"})
    if status != 200:
        return 0, 0, [f"Zwift workouts: server said {status}"]
    planned = json.loads(resp)
    if not isinstance(planned, list) or not all(isinstance(w, dict) for w in planned):
        return 0, 0, ["Zwift workouts: the server's reply wasn't a list of workouts; nothing changed."]

    state = dict(manifest)  # saved as we go
    ours = {k.lower(): k for k in manifest}  # APFS ignores case: "Z2 Ride.zwo" is our old "Z2 ride.zwo"
    keep: dict[str, str] = {}
    wanted: set[str] = set()  # every planned name, lower-cased, also the ones that couldn't be written this run
    in_place: list[int] = []
    written = removed = 0
    warnings: list[str] = []
    for w in planned:
        name = str(w.get("filename", ""))
        if not name.endswith(".zwo") or name.startswith(".") or "/" in name or "\\" in name:
            warnings.append(f"Zwift workouts: skipped an unsafe file name: {name!r}")
            continue
        wanted.add(name.lower())
        data = str(w.get("content", "")).encode()
        digest = _digest(data)
        path = folder / name
        was = ours.get(name.lower())  # the manifest's spelling of this name, if any
        try:
            if was is not None and was != name:  # the title's case changed: track it under the new spelling
                state[name] = state.pop(was)
                _save_manifest(folder, state)
            current = _digest(path.read_bytes()) if path.exists() else None
            if current is not None and current != digest:
                if was is None:
                    warnings.append(f"Zwift workouts: {name} already exists and isn't from LockedIn; left it alone.")
                    continue
                if manifest[was] == RELEASED:  # edited by the owner earlier; already told them
                    keep[name] = RELEASED
                    continue
                if current != manifest[was]:
                    warnings.append(f"Zwift workouts: {name} was changed in Zwift, so it's yours now; left it alone.")
                    state[name] = keep[name] = RELEASED
                    _save_manifest(folder, state)
                    continue
            if current != digest:
                _write_atomic(path, data)
                written += 1
            if state.get(name) != digest:  # also adopts an identical file from an interrupted run
                state[name] = digest
                _save_manifest(folder, state)
        except OSError as e:
            warnings.append(f"Zwift workouts: couldn't write {name}: {e}")
            continue
        keep[name] = digest
        if isinstance(w.get("item_id"), int):
            in_place.append(w["item_id"])

    kept = {k.lower(): k for k in keep}
    for name, digest in manifest.items():
        if name in keep:
            continue
        path = folder / name
        twin = kept.get(name.lower())
        if twin is None and name.lower() in wanted:
            continue  # still planned, just couldn't be written this time: keep it for the retry
        try:
            if twin is not None and path.exists() and os.path.samefile(path, folder / twin):
                pass  # the same file under its new spelling; nothing to remove
            elif path.exists() and _digest(path.read_bytes()) == digest:  # still exactly what this script wrote
                path.unlink()
                removed += 1
        except OSError as e:
            warnings.append(f"Zwift workouts: couldn't remove {name}, will retry: {e}")
            continue
        if twin is None:
            state.pop(name, None)
            _save_manifest(folder, state)

    status, _ = http(f"{api}/api/agenda/zwift/confirm", token, json.dumps({"item_ids": in_place}).encode(),
                     {"Content-Type": "application/json"})
    if status != 200:
        warnings.append(f"Zwift workouts: server said {status} when confirming; the agenda may still say pending.")
    return written, removed, warnings


def run(cfg: dict, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
        http: Http = urllib_http) -> list[SyncReport]:
    """Sync, then keep waiting a bit while files are still being written (launchd fires on the first write)."""
    reports = [sync_once(cfg, now(), http=http)]
    while reports[-1].pending and not reports[-1].stopped and len(reports) <= MAX_WAITS:
        sleep(WAIT_S)
        reports.append(sync_once(cfg, now(), http=http))
    last = reports[-1]
    try:
        last.workouts_written, last.workouts_removed, notes = sync_workouts(cfg, http)
        last.warnings += notes
    except Exception as e:  # never let workouts get in the way of uploads or the log line
        last.warnings.append(f"Zwift workouts: will retry next run: {e!r}")
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
              f"waiting (being written or downloading from iCloud) {report.pending}, errors {len(report.errors)}"
              f", Zwift workouts +{report.workouts_written} -{report.workouts_removed}")
        for line in report.warnings + report.errors:
            print(f"{stamp}   {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
