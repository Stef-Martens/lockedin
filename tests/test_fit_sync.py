import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fit_sync", ROOT / "sync" / "fit_sync.py")
fit_sync = importlib.util.module_from_spec(spec)
sys.modules["fit_sync"] = fit_sync  # dataclasses resolve string annotations via sys.modules
spec.loader.exec_module(fit_sync)

NOW = 1_800_000_000.0


def make(path: Path, data: bytes = b"fitdata", age_s: float = 3600) -> Path:
    path.write_bytes(data)
    os.utime(path, (NOW - age_s, NOW - age_s))
    return path


def test_skips_recent_hidden_icloud_and_large(tmp_path):
    ok = make(tmp_path / "ride.FIT")
    make(tmp_path / "recent.fit", age_s=10)
    make(tmp_path / ".hidden.fit")
    make(tmp_path / ".run.fit.icloud")
    make(tmp_path / "notes.txt")
    make(tmp_path / "huge.fit", data=b"x" * 4_000_001)
    files, warnings = fit_sync.candidate_files([(tmp_path, "zwift")], NOW)
    assert files == [(ok, "zwift")]
    assert any("huge.fit" in w for w in warnings)


def test_missing_and_unreadable_folder_warns_but_continues(tmp_path, monkeypatch):
    good = tmp_path / "good"; good.mkdir()
    blocked = tmp_path / "blocked"; blocked.mkdir()
    ride = make(good / "a.fit")
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == blocked:
            raise PermissionError("Operation not permitted")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    folders = [(blocked, "zwift"), (tmp_path / "missing", "healthfit"), (good, "healthfit")]
    files, warnings = fit_sync.candidate_files(folders, NOW)
    assert files == [(ride, "healthfit")]
    assert any("Full Disk Access" in w and str(blocked) in w for w in warnings)
    assert any("missing" in w for w in warnings)


class FakeHttp:
    def __init__(self, known=(), fail_on=None):
        self.known, self.fail_on, self.calls = set(known), fail_on, []

    def __call__(self, url, token, body, headers):
        self.calls.append((url, token, body, headers))
        if self.fail_on and self.fail_on in url:
            raise OSError("network down")
        if url.endswith("/api/fit/known"):
            hashes = json.loads(body)["hashes"]
            return 200, json.dumps({"known": [h for h in hashes if h in self.known]}).encode()
        return 200, json.dumps({"status": "imported"}).encode()


def cfg(folder):
    return {"LOCKEDIN_API": "https://x.test", "SYNC_TOKEN": "tok", "ZWIFT_ACTIVITIES_DIR": str(folder)}


def test_uploads_only_unknown(tmp_path):
    a = make(tmp_path / "a.fit", b"aaa")
    make(tmp_path / "b.fit", b"bbb")
    http = FakeHttp(known={fit_sync.sha256_file(a)})
    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=http)
    uploads = [c for c in http.calls if c[0].endswith("/api/fit/upload")]
    assert (report.uploaded, report.duplicates, report.errors) == (1, 1, [])
    assert len(uploads) == 1
    url, token, body, headers = uploads[0]
    assert token == "tok" and b'name="source"\r\n\r\nzwift' in body and b"bbb" in body
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")


def test_server_error_status_is_reported(tmp_path):
    make(tmp_path / "a.fit", b"aaa")

    def http(url, token, body, headers):
        if url.endswith("/known"):
            return 200, b'{"known": []}'
        return 200, b'{"status": "error", "error": "Could not read FIT file"}'

    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=http)
    assert report.uploaded == 0 and "a.fit" in report.errors[0]


def test_network_error_stops_run(tmp_path):
    make(tmp_path / "a.fit", b"aaa")
    make(tmp_path / "b.fit", b"bbb")
    http = FakeHttp(fail_on="/api/fit/upload")
    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=http)
    assert report.uploaded == 0
    assert len([c for c in http.calls if c[0].endswith("/upload")]) == 1
    assert report.errors and "network down" in report.errors[0]


def test_skips_zwift_in_progress_file(tmp_path):
    make(tmp_path / "inProgressActivity.fit")
    files, _ = fit_sync.candidate_files([(tmp_path, "zwift")], NOW)
    assert files == []


def test_run_waits_for_file_still_being_written(tmp_path):
    make(tmp_path / "ride.fit", b"ride", age_s=5)
    clock = {"t": NOW}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    http = FakeHttp()
    reports = fit_sync.run(cfg(tmp_path), now=lambda: clock["t"], sleep=sleep, http=http)
    assert sum(r.uploaded for r in reports) == 1
    assert sleeps and len(reports) == 2


def test_run_gives_up_after_max_waits(tmp_path):
    p = make(tmp_path / "ride.fit", b"ride", age_s=0)
    clock = {"t": NOW}

    def sleep(s):
        clock["t"] += s
        os.utime(p, (clock["t"], clock["t"]))  # file keeps changing

    reports = fit_sync.run(cfg(tmp_path), now=lambda: clock["t"], sleep=sleep, http=FakeHttp())
    assert len(reports) == fit_sync.MAX_WAITS + 1 and sum(r.uploaded for r in reports) == 0


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="macOS system python only")
def test_script_runs_on_macos_system_python(tmp_path):
    import subprocess
    env = {"HOME": str(tmp_path), "LOCKEDIN_API": "http://127.0.0.1:1", "SYNC_TOKEN": "x",
           "ZWIFT_ACTIVITIES_DIR": str(tmp_path)}
    out = subprocess.run(["/usr/bin/python3", str(ROOT / "sync" / "fit_sync.py")], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "uploaded 0" in out.stdout
