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


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    """Defaults like ~/Documents/Zwift/Workouts must never reach the real home folder in tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


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


def test_folder_whose_stat_is_blocked_warns_and_continues(tmp_path, monkeypatch):
    good = tmp_path / "good"; good.mkdir()
    blocked = tmp_path / "blocked"; blocked.mkdir()
    ride = make(good / "a.fit")
    real_is_dir = Path.is_dir

    def is_dir(self):
        if self == blocked:
            raise PermissionError(1, "Operation not permitted")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    files, warnings = fit_sync.candidate_files([(blocked, "zwift"), (good, "healthfit")], NOW)
    assert files == [(ride, "healthfit")]
    assert any("Full Disk Access" in w for w in warnings)


def test_unreadable_file_is_skipped_with_warning(tmp_path, monkeypatch):
    bad = make(tmp_path / "a.fit", b"aaa")
    make(tmp_path / "b.fit", b"bbb")
    real = fit_sync.sha256_file

    def sha(path):
        if path == bad:
            raise OSError("Resource deadlock avoided")  # e.g. iCloud file that won't download
        return real(path)

    monkeypatch.setattr(fit_sync, "sha256_file", sha)
    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=FakeHttp())
    assert report.uploaded == 1 and any("a.fit" in w for w in report.warnings)


def test_server_error_on_one_file_does_not_block_the_rest(tmp_path):
    make(tmp_path / "a.fit", b"aaa")
    make(tmp_path / "b.fit", b"bbb")

    def http(url, token, body, headers):
        if url.endswith("/known"):
            return 200, b'{"known": []}'
        if b'filename="a.fit"' in body:  # not the content: the random multipart boundary can contain "aaa"
            return 500, b"Internal Server Error"
        return 200, b'{"status": "imported"}'

    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=http)
    assert report.uploaded == 1 and len(report.errors) == 1 and "a.fit" in report.errors[0]


def test_main_logs_a_line_even_when_something_unexpected_breaks(monkeypatch, capsys):
    def explode(cfg):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(fit_sync, "run", explode)
    monkeypatch.setattr(fit_sync, "load_config", lambda: {})
    assert fit_sync.main() == 0
    assert "kaboom" in capsys.readouterr().out


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="macOS system python only")
def test_install_uses_the_real_interpreter_and_names_it(tmp_path):
    import plistlib
    import subprocess
    home = tmp_path / "home"
    (home / ".config" / "lockedin").mkdir(parents=True)
    (home / ".config" / "lockedin" / "sync.env").write_text("LOCKEDIN_API=http://x\nSYNC_TOKEN=t\n")
    stub = tmp_path / "bin"; stub.mkdir()
    (stub / "launchctl").write_text("#!/bin/sh\nexit 0\n"); (stub / "launchctl").chmod(0o755)
    out = subprocess.run(["bash", str(ROOT / "sync" / "install.sh")], capture_output=True, text=True,
                         env={"HOME": str(home), "PATH": f"{stub}:/usr/bin:/bin"}, timeout=60)
    assert out.returncode == 0, out.stderr
    real = subprocess.run(["/usr/bin/python3", "-c", "import os,sys;print(os.path.realpath(sys.executable))"],
                          capture_output=True, text=True).stdout.strip()
    plist = plistlib.loads((home / "Library" / "LaunchAgents" / "com.lockedin.fitsync.plist").read_bytes())
    assert plist["ProgramArguments"][0] == real
    assert real in out.stdout and "Full Disk Access" in out.stdout


def test_icloud_evicted_file_is_downloaded_and_retried(tmp_path, monkeypatch):
    import errno
    evicted = make(tmp_path / "old.fit", b"old ride")
    state = {"downloaded": False}
    requested = []
    real = fit_sync.sha256_file

    def sha(path):
        if path == evicted and not state["downloaded"]:
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")  # iCloud placeholder
        return real(path)

    def download(path):
        requested.append(path)
        state["downloaded"] = True

    monkeypatch.setattr(fit_sync, "sha256_file", sha)
    monkeypatch.setattr(fit_sync, "icloud_download", download)
    first = fit_sync.sync_once(cfg(tmp_path), NOW, http=FakeHttp())
    assert requested == [evicted]
    assert first.pending == 1 and first.uploaded == 0 and first.warnings == []
    second = fit_sync.sync_once(cfg(tmp_path), NOW, http=FakeHttp())
    assert second.uploaded == 1


def test_empty_upload_is_not_an_error(tmp_path):
    make(tmp_path / "a.fit", b"aaa")

    def http(url, token, body, headers):
        if url.endswith("/known"):
            return 200, b'{"known": []}'
        return 200, b'{"status": "empty"}'

    report = fit_sync.sync_once(cfg(tmp_path), NOW, http=http)
    assert report.errors == [] and report.duplicates == 1


# --- Zwift workouts from the agenda -----------------------------------------------------------------

ZWO = "<workout_file><name>{}</name></workout_file>\n"


def zwift_cfg(tmp_path, activities=None):
    folder = tmp_path / "Workouts" / "8171441"
    folder.mkdir(parents=True)
    acts = activities or (tmp_path / "Activities")
    acts.mkdir(exist_ok=True)
    return {"LOCKEDIN_API": "https://x.test", "SYNC_TOKEN": "tok", "ZWIFT_ACTIVITIES_DIR": str(acts),
            "ZWIFT_WORKOUTS_DIR": str(tmp_path / "Workouts")}, folder


class Feed:
    def __init__(self, served):
        self.served = served
        self.calls = 0
        self.confirmed = None

    def __call__(self, url, token, body, headers):
        if url.endswith("/api/agenda/zwift/sync"):
            self.calls += 1
            return 200, json.dumps(self.served).encode()
        if url.endswith("/api/agenda/zwift/confirm"):
            self.confirmed = json.loads(body)["item_ids"]
            return 200, b"{}"
        if url.endswith("/known"):
            return 200, b'{"known": []}'
        return 200, b'{"status": "imported"}'


def served(*names):
    return [{"item_id": i, "filename": n, "content": ZWO.format(n)} for i, n in enumerate(names, 1)]


def test_writes_planned_workouts_and_a_manifest(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    feed = Feed(served("2026-10-26 Recovery Spin 30.zwo", "2026-10-29 Sweet Spot 3x10.zwo"))
    assert fit_sync.sync_workouts(cfg, feed)[:2] == (2, 0)
    assert (folder / "2026-10-29 Sweet Spot 3x10.zwo").read_text() == ZWO.format("2026-10-29 Sweet Spot 3x10.zwo")
    manifest = json.loads((folder / ".lockedin-workouts.json").read_text())
    assert set(manifest) == {"2026-10-26 Recovery Spin 30.zwo", "2026-10-29 Sweet Spot 3x10.zwo"}
    assert fit_sync.sync_workouts(cfg, feed)[:2] == (0, 0)  # unchanged: nothing rewritten


def test_removes_only_its_own_unmodified_files(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    fit_sync.sync_workouts(cfg, Feed(served("a.zwo", "b.zwo", "c.zwo")))
    (folder / "b.zwo").write_text("<workout_file>edited by hand</workout_file>")
    (folder / "mine.zwo").write_text("<workout_file>my own</workout_file>")
    written, removed, _ = fit_sync.sync_workouts(cfg, Feed(served("c.zwo")))
    assert (written, removed) == (0, 1)
    assert not (folder / "a.zwo").exists()
    assert (folder / "b.zwo").exists() and (folder / "mine.zwo").exists()  # edited and foreign files stay
    assert set(json.loads((folder / ".lockedin-workouts.json").read_text())) == {"c.zwo"}


def test_never_overwrites_a_file_it_did_not_write(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    (folder / "a.zwo").write_text("<workout_file>my own</workout_file>")
    written, _, warnings = fit_sync.sync_workouts(cfg, Feed(served("a.zwo")))
    assert written == 0 and "my own" in (folder / "a.zwo").read_text() and warnings


def test_rejects_unsafe_names(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    written, _, warnings = fit_sync.sync_workouts(cfg, Feed(served("../escape.zwo", ".hidden.zwo", "sub/x.zwo")))
    assert written == 0 and len(warnings) == 3
    assert not (tmp_path / "Workouts" / "escape.zwo").exists()


def test_no_zwift_folder_means_no_call(tmp_path):
    feed = Feed(served("a.zwo"))
    cfg = {"LOCKEDIN_API": "https://x.test", "SYNC_TOKEN": "tok", "ZWIFT_WORKOUTS_DIR": str(tmp_path / "nope")}
    assert fit_sync.sync_workouts(cfg, feed)[2] and feed.calls == 0
    (tmp_path / "two" / "111").mkdir(parents=True)
    (tmp_path / "two" / "222").mkdir(parents=True)
    cfg["ZWIFT_WORKOUTS_DIR"] = str(tmp_path / "two")
    assert fit_sync.sync_workouts(cfg, feed)[2] and feed.calls == 0


def test_feed_errors_never_block_uploads(tmp_path):
    cfg, _ = zwift_cfg(tmp_path)
    make(Path(cfg["ZWIFT_ACTIVITIES_DIR"]) / "ride.fit", b"ride")

    def http(url, token, body, headers):
        if url.endswith("/zwift/sync"):
            raise OSError("network down")
        if url.endswith("/known"):
            return 200, b'{"known": []}'
        return 200, b'{"status": "imported"}'

    reports = fit_sync.run(cfg, now=lambda: NOW, sleep=lambda s: None, http=http)
    assert reports[-1].uploaded == 1 and not reports[-1].errors
    assert any("Zwift workouts" in w for w in reports[-1].warnings)


def test_run_reports_workouts(tmp_path):
    cfg, _ = zwift_cfg(tmp_path)
    reports = fit_sync.run(cfg, now=lambda: NOW, sleep=lambda s: None, http=Feed(served("a.zwo")))
    assert (reports[-1].workouts_written, reports[-1].workouts_removed) == (1, 0)


def test_plist_runs_every_15_minutes():
    plist = (ROOT / "sync" / "com.lockedin.fitsync.plist.template").read_text()
    assert "<integer>900</integer>" in plist


def test_never_overwrites_an_edited_lockedin_file(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    fit_sync.sync_workouts(cfg, Feed(served("a.zwo")))
    (folder / "a.zwo").write_text("<workout_file>tweaked in Zwift's editor</workout_file>")
    changed = [{"item_id": 1, "filename": "a.zwo", "content": "<workout_file>new plan</workout_file>"}]
    feed = Feed(changed)
    written, _, warnings = fit_sync.sync_workouts(cfg, feed)
    assert written == 0 and "tweaked" in (folder / "a.zwo").read_text() and warnings
    assert feed.confirmed == []  # not in Zwift as planned, so not confirmed


def test_confirms_only_what_is_in_place(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    (folder / "taken.zwo").write_text("<workout_file>my own</workout_file>")
    feed = Feed([{"item_id": 7, "filename": "ok.zwo", "content": "x"}, {"item_id": 8, "filename": "taken.zwo", "content": "y"},
                 {"item_id": 9, "filename": "../bad.zwo", "content": "z"}])
    fit_sync.sync_workouts(cfg, feed)
    assert feed.confirmed == [7]
    fit_sync.sync_workouts(cfg, feed)  # unchanged on the second run, still in place
    assert feed.confirmed == [7]


def test_adopts_identical_files_after_an_interrupted_run(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    (folder / "a.zwo").write_text(ZWO.format("a.zwo"))  # written last time, but the manifest never got saved
    written, _, warnings = fit_sync.sync_workouts(cfg, Feed(served("a.zwo")))
    assert written == 0 and not warnings
    assert "a.zwo" in json.loads((folder / ".lockedin-workouts.json").read_text())
    fit_sync.sync_workouts(cfg, Feed([]))
    assert not (folder / "a.zwo").exists()  # now ours: removed once it's no longer planned


def test_one_bad_file_doesnt_stop_the_others_and_the_manifest_keeps_up(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    (folder / "b.zwo").mkdir()  # can't be written
    feed = Feed(served("a.zwo", "b.zwo", "c.zwo"))
    written, _, warnings = fit_sync.sync_workouts(cfg, feed)
    assert written == 2 and warnings
    assert set(json.loads((folder / ".lockedin-workouts.json").read_text())) == {"a.zwo", "c.zwo"}
    assert feed.confirmed == [1, 3]


def test_a_damaged_manifest_means_hands_off(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    (folder / ".lockedin-workouts.json").write_text("[]")
    feed = Feed(served("a.zwo"))
    written, removed, warnings = fit_sync.sync_workouts(cfg, feed)
    assert (written, removed) == (0, 0) and warnings and feed.calls == 0


def test_an_edited_lockedin_file_is_left_alone_quietly_after_the_first_note(tmp_path):
    cfg, folder = zwift_cfg(tmp_path)
    fit_sync.sync_workouts(cfg, Feed(served("a.zwo")))
    (folder / "a.zwo").write_text("<workout_file>tweaked in Zwift's editor</workout_file>")
    changed = [{"item_id": 1, "filename": "a.zwo", "content": "<workout_file>new plan</workout_file>"}]
    assert fit_sync.sync_workouts(cfg, Feed(changed))[2]  # told once
    written, _, warnings = fit_sync.sync_workouts(cfg, Feed(changed))
    assert written == 0 and warnings == [] and "tweaked" in (folder / "a.zwo").read_text()
    fit_sync.sync_workouts(cfg, Feed([]))  # no longer planned: still the owner's file
    assert "tweaked" in (folder / "a.zwo").read_text()
    assert "a.zwo" not in json.loads((folder / ".lockedin-workouts.json").read_text())
