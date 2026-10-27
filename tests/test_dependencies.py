"""pyproject.toml is the one list of dependencies; uv.lock (what Vercel installs) and requirements.txt pin it."""

import re
import tomllib

from conftest import ROOT

UNBOUNDED = {"tzdata"}  # calendar-versioned data, newer is always fine


def name(req: str) -> str:
    return re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]+", req.strip()).group()).lower()


def pyproject_deps() -> list[str]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]


def requirement_pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split(";")[0].strip()
        if line and not line.startswith("#"):
            assert "==" in line, f"not pinned: {line}"
            pkg, version = line.split("==")
            pins[name(pkg)] = version.strip()
    return pins


def test_every_runtime_dependency_is_pinned_in_requirements():
    pins = requirement_pins()
    missing = [d for d in pyproject_deps() if name(d) not in pins]
    assert not missing, f"run `make lock`: {missing}"


def test_requirements_match_uv_lock():
    locked = {name(p["name"]): p["version"] for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]
              if "version" in p}
    stale = {k: (v, locked.get(k)) for k, v in requirement_pins().items() if locked.get(k) != v}
    assert not stale, f"run `make lock`: {stale}"


def test_runtime_dependencies_stay_below_the_next_major():
    unbounded = [d for d in pyproject_deps() if "<" not in d and name(d) not in UNBOUNDED]
    assert not unbounded, unbounded
